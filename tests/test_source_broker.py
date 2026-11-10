"""B5/B2 negative tests: fixed-ID Unix RPC never grants shell/UI or replay."""
import json
import os
from pathlib import Path
import socket
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from remote_security.source_broker import SourceBroker, Rejected, parse_request, MAX_REQUEST


def frame(action="capture", source_id="rustworld-world", job_id="source0001"):
    return (json.dumps({"version": 1, "action": action, "source_id": source_id,
                        "job_id": job_id}, separators=(",", ":")) + "\n").encode()


class RequestTests(unittest.TestCase):
    def test_strict_frame(self):
        self.assertEqual(parse_request(frame(), {"rustworld-world"})["job_id"], "source0001")
        for raw in (b"", b"{}", b"{}\n\n", b"[]\n", b"{\"version\":NaN}\n",
                    b"{" + b"x" * MAX_REQUEST + b"}\n",
                    b'{"version":1,"version":1}\n',
                    frame()[:-1] + b"garbage\n", frame().replace(b"capture", b"execute"),
                    frame().replace(b"source0001", b"../escape"),
                    frame().replace(b"rustworld-world", b"other-source"),
                    frame().replace(b'"version":1', b'"version":true'),
                    frame()[:-1] + b"\n" + frame()):
            with self.subTest(raw=raw[:70]), self.assertRaises(Rejected):
                parse_request(raw, {"rustworld-world"})


@unittest.skipUnless(os.name == "posix" and hasattr(socket, "SO_PEERCRED"), "Linux only")
class BrokerTests(unittest.TestCase):
    def setUp(self):
        if os.geteuid() == 0:
            self.skipTest("run as non-root for actual socket owner checks")
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.base.chmod(0o710)
        self.path = self.base / "broker.sock"
        self.calls = []
        def capture(s, j):
            self.calls.append(("capture", s, j))
            return {"state": "completed_local_pinned_source", "source_sha256": "a" * 64}
        def audit(s, j):
            self.calls.append(("audit", s, j))
            return {"state": "verified_local_pinned_source", "source_sha256": "a" * 64}
        self.allowed = os.geteuid() + 1
        self.broker = SourceBroker(str(self.path), {self.allowed}, {"rustworld-world"}, capture, audit)
        self.broker.start()
        self.addCleanup(self.broker.close)

    def exchange(self, raw, authorized=True):
        with patch.object(self.broker, "_peer_uid", return_value=self.allowed if authorized else os.geteuid()):
            thread = threading.Thread(target=self.broker.accept_once, daemon=True)
            thread.start()
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
                s.settimeout(2)
                s.connect(str(self.path))
                s.sendall(raw)
                s.shutdown(socket.SHUT_WR)
                try:
                    result = s.recv(4096)
                except ConnectionResetError:
                    result = b""  # kernel rejects a peer before consuming its request
            thread.join(2)
            self.assertFalse(thread.is_alive())
            return result

    def test_capture_and_audit_only_fixed_ids(self):
        self.assertEqual(json.loads(self.exchange(frame()))["state"], "completed_local_pinned_source")
        self.assertEqual(json.loads(self.exchange(frame("audit")))["state"], "verified_local_pinned_source")
        self.assertEqual(self.calls, [("capture", "rustworld-world", "source0001"),
                                      ("audit", "rustworld-world", "source0001")])

    def test_unauthorized_uid_rejected_before_read(self):
        self.assertEqual(self.exchange(frame(), authorized=False), b"")
        self.assertEqual(self.calls, [])

    def test_forged_commands_and_extra_fields_rejected(self):
        for raw in (frame("delete"), frame(source_id="other-source"),
                    b'{"version":1,"action":"capture","source_id":"rustworld-world","job_id":"source0001","path":"/etc/passwd"}\n'):
            self.assertEqual(json.loads(self.exchange(raw))["state"], "rejected_or_uncertain_no_retry")
        self.assertEqual(self.calls, [])

    def test_fragmented_second_frame_rejected_before_execution(self):
        import time
        with patch.object(self.broker, "_peer_uid", return_value=self.allowed):
            thread = threading.Thread(target=self.broker.accept_once, daemon=True)
            thread.start()
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                sock.settimeout(2)
                sock.connect(str(self.path))
                sock.sendall(frame())
                time.sleep(0.02)  # second frame arrives after first read
                sock.sendall(frame("audit"))
                sock.shutdown(socket.SHUT_WR)
                result = sock.recv(4096)
            thread.join(2)
            self.assertFalse(thread.is_alive())
            self.assertEqual(json.loads(result)["state"], "rejected_or_uncertain_no_retry")
            self.assertEqual(self.calls, [])

    def test_authorized_slow_trickle_cannot_hold_single_threaded_broker(self):
        # The caller has a permitted UID but never completes a JSON frame.
        # A per-recv timeout would be reset by each byte indefinitely.
        with patch.object(self.broker, "_peer_uid", return_value=self.allowed), \
                patch("remote_security.source_broker.READ_DEADLINE_SECONDS", 0.20):
            worker = threading.Thread(target=self.broker.accept_once, daemon=True)
            worker.start()
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                client.settimeout(1)
                client.connect(str(self.path))
                start = time.monotonic()
                for _ in range(16):
                    if not worker.is_alive():
                        break
                    try:
                        client.sendall(b"x")
                    except (BrokenPipeError, ConnectionResetError):
                        break
                    time.sleep(0.04)
                worker.join(0.25)
                self.assertFalse(worker.is_alive(), "trickle must not keep broker occupied")
                self.assertLess(time.monotonic() - start, 0.8)
        self.assertEqual(self.calls, [])

    def test_backend_failure_uncertain_never_retry(self):
        def uncertain(_s, _j):
            self.calls.append("reserved")
            raise RuntimeError("may have executed")
        self.broker.capture = uncertain
        self.assertEqual(json.loads(self.exchange(frame()))["state"], "rejected_or_uncertain_no_retry")
        self.assertEqual(self.calls, ["reserved"])

    def test_socket_restart_refuses_stale_endpoint(self):
        other = SourceBroker(str(self.path), {self.allowed}, {"rustworld-world"}, self.broker.capture, self.broker.audit)
        with self.assertRaises(Rejected):
            other.start()
        self.assertTrue(self.path.exists())

    def test_symlink_ancestor_rejected(self):
        link = self.base / "link"
        link.symlink_to(self.base, target_is_directory=True)
        with self.assertRaises(Rejected):
            SourceBroker(str(link / "other.sock"), {self.allowed}, {"rustworld-world"},
                         self.broker.capture, self.broker.audit)

    def test_world_accessible_parent_rejected(self):
        self.base.chmod(0o711)
        with self.assertRaises(Rejected):
            SourceBroker(str(self.base / "other.sock"), {self.allowed}, {"rustworld-world"},
                         self.broker.capture, self.broker.audit)

    def test_same_uid_and_root_allowed_uid_refused(self):
        for uids in ({os.geteuid()}, {0}, set()):
            with self.subTest(uids=uids), self.assertRaises(Rejected):
                SourceBroker(str(self.base / "other.sock"), uids, {"rustworld-world"},
                             self.broker.capture, self.broker.audit)

    def test_no_tcp_listener_and_mode(self):
        st = self.path.lstat()
        self.assertTrue(stat_is_socket(st.st_mode))
        self.assertEqual(st.st_mode & 0o777, 0o660)
        self.assertEqual(self.broker.sock.family, socket.AF_UNIX)


def stat_is_socket(mode):
    import stat
    return stat.S_ISSOCK(mode)


@unittest.skipUnless(os.name == "posix" and os.geteuid() == 0 and hasattr(os, "fork"),
                     "root-only isolated two-UID kernel credential test")
class CrossUidTests(unittest.TestCase):
    def test_actual_linux_peer_uid_and_forged_sender(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            root.chmod(0o755)
            parent = root / "socketdir"
            parent.mkdir()
            os.chown(parent, 21001, 21002)
            parent.chmod(0o710)
            path = parent / "broker.sock"
            ready_r, ready_w = os.pipe()
            server = os.fork()
            if server == 0:
                try:
                    os.close(ready_r)
                    os.setgid(21002)
                    os.setuid(21001)
                    broker = SourceBroker(str(path), {21003}, {"rustworld-world"},
                                          lambda _s, _j: {"state": "completed_local_pinned_source"},
                                          lambda _s, _j: {"state": "verified_local_pinned_source"})
                    broker.start()
                    os.write(ready_w, b"R")
                    broker.accept_once()
                    broker.accept_once()
                    broker.close()
                    os._exit(0)
                except BaseException:
                    os._exit(3)
            os.close(ready_w)
            try:
                self.assertEqual(os.read(ready_r, 1), b"R")
                def client(uid):
                    pipe_r, pipe_w = os.pipe()
                    pid = os.fork()
                    if pid == 0:
                        try:
                            os.close(pipe_r)
                            os.setgid(21002)
                            os.setuid(uid)
                            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                                sock.settimeout(2)
                                sock.connect(str(path))
                                try:
                                    sock.sendall(frame())
                                    sock.shutdown(socket.SHUT_WR)
                                    data = sock.recv(4096)
                                except (ConnectionResetError, BrokenPipeError):
                                    data = b""
                            os.write(pipe_w, data or b"DENIED")
                            os._exit(0)
                        except BaseException:
                            os._exit(4)
                    os.close(pipe_w)
                    data = os.read(pipe_r, 4096)
                    os.close(pipe_r)
                    _, status = os.waitpid(pid, 0)
                    self.assertEqual(os.waitstatus_to_exitcode(status), 0)
                    return data
                self.assertEqual(json.loads(client(21003))["state"], "completed_local_pinned_source")
                self.assertEqual(client(21004), b"DENIED")
                _, status = os.waitpid(server, 0)
                self.assertEqual(os.waitstatus_to_exitcode(status), 0)
            finally:
                os.close(ready_r)
                try:
                    os.kill(server, 9)
                    os.waitpid(server, 0)
                except (ProcessLookupError, ChildProcessError):
                    pass
