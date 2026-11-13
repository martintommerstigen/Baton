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

    def test_failed_chmod_rolls_back_only_new_socket_and_allows_restart(self):
        # The endpoint is bound before chmod; a failed startup must not strand
        # a dead socket requiring manual deletion or an unsafe blind unlink.
        path = self.base / "failed.sock"
        other = SourceBroker(str(path), {self.allowed}, {"rustworld-world"},
                             self.broker.capture, self.broker.audit)
        with patch("remote_security.source_broker.os.chmod",
                   side_effect=PermissionError("synthetic chmod failure")):
            with self.assertRaises(PermissionError):
                other.start()
        self.assertFalse(path.exists(), "own newly bound socket should be rolled back")
        self.assertIsNone(other.sock)
        other.start()
        self.assertTrue(stat_is_socket(path.lstat().st_mode))
        other.close()
        self.assertFalse(path.exists())

    def test_failed_listen_rolls_back_only_own_socket(self):
        path = self.base / "listen-failed.sock"
        other = SourceBroker(str(path), {self.allowed}, {"rustworld-world"},
                             self.broker.capture, self.broker.audit)
        with patch.object(socket.socket, "listen", side_effect=OSError("synthetic listen failure")):
            with self.assertRaises(OSError):
                other.start()
        self.assertFalse(path.exists())
        self.assertIsNone(other.sock)
        other.start()
        other.close()

    def test_failed_start_never_unlinks_replaced_endpoint(self):
        # A path changed between bind and chmod must not be unlinked by the
        # cleanup path. No assertion of safety against same-UID compromise.
        path = self.base / "replaced.sock"
        other = SourceBroker(str(path), {self.allowed}, {"rustworld-world"},
                             self.broker.capture, self.broker.audit)
        def replace_and_fail(socket_path, _mode, **kwargs):
            os.unlink(socket_path, dir_fd=kwargs["dir_fd"])
            path.write_text("replacement belongs to another inode")
            raise PermissionError("synthetic post-bind replacement")
        with patch("remote_security.source_broker.os.chmod", side_effect=replace_and_fail):
            with self.assertRaises(PermissionError):
                other.start()
        self.assertEqual(path.read_text(), "replacement belongs to another inode")
        self.assertIsNone(other.sock)
        with self.assertRaises(Rejected):
            other.start()

    def test_parent_replacement_before_start_is_rejected(self):
        parent = self.base / "prestart"
        parent.mkdir(mode=0o710)
        path = parent / "guard.sock"
        other = SourceBroker(str(path), {self.allowed}, {"rustworld-world"},
                             self.broker.capture, self.broker.audit)
        parent.rename(self.base / "old-prestart")
        parent.mkdir(mode=0o710)  # same owner/mode, different inode
        with self.assertRaises(Rejected):
            other.start()
        self.assertFalse(path.exists())
        self.assertFalse((self.base / "old-prestart" / "guard.sock").exists())

    def test_parent_swap_between_validation_and_bind_is_anchored_and_rejected(self):
        parent = self.base / "swap-parent"
        parent.mkdir(mode=0o710)
        moved = self.base / "moved-parent"
        decoy = self.base / "decoy"
        decoy.mkdir(mode=0o710)
        path = parent / "guard.sock"
        other = SourceBroker(str(path), {self.allowed}, {"rustworld-world"},
                             self.broker.capture, self.broker.audit)
        real_bind = socket.socket.bind
        swaps = []
        def swap_before_bind(sock, address):
            parent.rename(moved)
            parent.symlink_to(decoy, target_is_directory=True)
            swaps.append(address)
            return real_bind(sock, address)
        with patch.object(socket.socket, "bind", new=swap_before_bind):
            with self.assertRaises(Rejected):
                other.start()
        self.assertEqual(len(swaps), 1)
        self.assertIn("/proc/self/fd/", swaps[0])
        self.assertFalse((decoy / "guard.sock").exists(),
                         "never bind into a replaced directory")
        self.assertFalse((moved / "guard.sock").exists(),
                         "rollback must target the original pinned directory")
        self.assertIsNone(other.sock)
        self.assertIsNone(other.parent_fd)

    def test_parent_swap_after_start_fails_closed_and_preserves_replacement(self):
        parent = self.base / "live-parent"
        parent.mkdir(mode=0o710)
        moved = self.base / "moved-live-parent"
        path = parent / "guard.sock"
        other = SourceBroker(str(path), {self.allowed}, {"rustworld-world"},
                             self.broker.capture, self.broker.audit)
        other.start()
        parent.rename(moved)
        parent.mkdir(mode=0o710)
        replacement = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            replacement.bind(str(path))
            with self.assertRaises(Rejected):
                other.accept_once()  # must not process a request at the stale path
            other.close()
            self.assertTrue(path.exists(), "never unlink replacement")
            self.assertFalse((moved / "guard.sock").exists(),
                             "cleanup must use pinned original directory")
        finally:
            replacement.close()
            other.close()

    def test_parent_swap_inside_blocking_accept_rejects_before_request_read(self):
        parent = self.base / "accept-parent"
        parent.mkdir(mode=0o710)
        moved = self.base / "moved-accept-parent"
        path = parent / "guard.sock"
        other = SourceBroker(str(path), {self.allowed}, {"rustworld-world"},
                             self.broker.capture, self.broker.audit)
        other.start()
        real_accept = socket.socket.accept
        def accept_and_move(sock):
            conn, address = real_accept(sock)
            parent.rename(moved)
            parent.mkdir(mode=0o710)
            return conn, address
        try:
            with patch.object(socket.socket, "accept", new=accept_and_move), \
                    patch.object(other, "_peer_uid", return_value=self.allowed):
                worker = threading.Thread(target=other.accept_once, daemon=True)
                worker.start()
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                    client.settimeout(2)
                    client.connect(str(path))
                    client.sendall(frame())
                    client.shutdown(socket.SHUT_WR)
                    try:
                        self.assertEqual(client.recv(4096), b"")
                    except ConnectionResetError:
                        pass
                worker.join(2)
                self.assertFalse(worker.is_alive())
            self.assertEqual(self.calls, [], "no backend after accepted socket moved")
        finally:
            other.close()
        self.assertFalse((moved / "guard.sock").exists())

    def test_parent_swap_after_frame_parse_rejects_before_backend(self):
        parent = self.base / "parse-parent"
        parent.mkdir(mode=0o710)
        moved = self.base / "moved-parse-parent"
        path = parent / "guard.sock"
        other = SourceBroker(str(path), {self.allowed}, {"rustworld-world"},
                             self.broker.capture, self.broker.audit)
        other.start()
        real_parse = parse_request
        def parse_and_move(raw, ids):
            result = real_parse(raw, ids)
            parent.rename(moved)
            parent.mkdir(mode=0o710)
            return result
        try:
            with patch("remote_security.source_broker.parse_request", side_effect=parse_and_move), \
                    patch.object(other, "_peer_uid", return_value=self.allowed):
                worker = threading.Thread(target=other.accept_once, daemon=True)
                worker.start()
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                    client.settimeout(2)
                    client.connect(str(path))
                    client.sendall(frame())
                    client.shutdown(socket.SHUT_WR)
                    response = client.recv(4096)
                worker.join(2)
                self.assertFalse(worker.is_alive())
            self.assertEqual(json.loads(response)["state"], "rejected_or_uncertain_no_retry")
            self.assertEqual(self.calls, [], "no backend after parsed frame moved")
        finally:
            other.close()
        self.assertFalse((moved / "guard.sock").exists())

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
