"""B1/B5 real Linux kernel two-UID AF_UNIX admission test; isolated CI only.

Run explicitly as root in a disposable CI runner. The service and clients drop
to unrelated numeric UIDs; no user accounts, network, browser or secrets.
This checks server-side SO_PEERCRED, NOT ChatGPT source-turn identity or
the separately maintained B5 verified client.
"""
import json
import os
from pathlib import Path
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import time
import unittest

from wake_admission_broker import AdmissionStore, Broker

SERVICE_UID = 60001
UI_UID = 60002
SHARED_GID = 60003
WRONG_UID = 60004


@unittest.skipUnless(os.geteuid() == 0 and hasattr(socket, "SO_PEERCRED"),
                     "isolated root-run Linux kernel test only")
class CrossUIDBrokerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        # Root-owned parent permits traversal, not writing, by the two UIDs.
        self.root.chmod(0o711)
        self.sock_dir = self.root / "shared"
        self.sock_dir.mkdir(mode=0o710)
        os.chown(self.sock_dir, SERVICE_UID, SHARED_GID)
        self.sock_dir.chmod(0o710)
        self.db_dir = self.root / "private"
        self.db_dir.mkdir(mode=0o700)
        os.chown(self.db_dir, SERVICE_UID, SERVICE_UID)
        self.db_dir.chmod(0o700)
        self.sock = self.sock_dir / "broker.sock"
        self.db = self.db_dir / "admissions.sqlite"
        self.pause = self.db_dir / "PAUSE_UI_WRITES"
        self.pid = None
        self.addCleanup(self.stop_server)

    def start_server(self):
        pid = os.fork()
        if pid == 0:
            try:
                os.setgroups([SHARED_GID])
                os.setgid(SERVICE_UID)
                os.setuid(SERVICE_UID)
                store = AdmissionStore(self.db, self.pause, ["chat-B", "chat-C"])
                with Broker(self.sock, store, [UI_UID], shared_gid=SHARED_GID) as server:
                    server.serve_forever(poll_interval=0.01)
            except BaseException:
                os._exit(111)
            os._exit(0)
        self.pid = pid
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            exited, status = os.waitpid(pid, os.WNOHANG)
            if exited:
                self.pid = None
                self.fail(f"broker service failed before bind: {status}")
            if self.sock.exists():
                st = self.sock.stat()
                if stat.S_ISSOCK(st.st_mode) and stat.S_IMODE(st.st_mode) == 0o660:
                    self.assertEqual(st.st_uid, SERVICE_UID)
                    self.assertEqual(st.st_gid, SHARED_GID)
                    return
            time.sleep(0.02)
        self.fail("broker did not bind a 0660 socket")

    def stop_server(self):
        if self.pid is not None:
            try:
                os.kill(self.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                os.waitpid(self.pid, 0)
            except ChildProcessError:
                pass
            self.pid = None
        # The root-only test harness clears its own stale socket after death.
        self.sock.unlink(missing_ok=True)

    def query_as(self, uid, request, *, expect_success=True):
        # The isolated client deliberately uses B1's unverified query() only
        # to test server-side kernel UID admission. Never use it in live UI.
        # A standalone test client avoids importing source from the runner's
        # private checkout directory after dropping to an unrelated UID.
        frame = (json.dumps(request, sort_keys=True) + "\n").encode("utf-8")
        code = ("import json,socket; s=socket.socket(socket.AF_UNIX); "
                "s.connect(" + repr(str(self.sock)) + "); "
                "s.sendall(" + repr(frame) + "); "
                "s.shutdown(socket.SHUT_WR); "
                "data=s.recv(8192); s.close(); print(json.dumps(json.loads(data)))")
        def drop():
            os.setgroups([SHARED_GID])
            os.setgid(uid)
            os.setuid(uid)
        proc = subprocess.run([sys.executable, "-c", code],
                              cwd=Path(__file__).resolve().parents[1],
                              preexec_fn=drop, capture_output=True, text=True,
                              timeout=7)
        if expect_success:
            self.assertEqual(proc.returncode, 0, proc.stderr)
            return json.loads(proc.stdout)
        self.assertNotEqual(proc.returncode, 0)
        return None

    def test_real_two_uid_admit_wrong_uid_restart_and_no_retry(self):
        self.start_server()
        envelope = {
            "conversation_id": "chat-B", "message_id": "m1",
            "origin_turn_id": "turn-A", "sender_id": "chat-A",
            "payload_sha256": "a" * 64,
        }
        self.assertEqual(self.query_as(UI_UID, {"op": "status"}),
                         {"state": "ready", "outstanding": 0})
        self.assertEqual(self.query_as(UI_UID, {"op": "admit", **envelope}),
                         {"state": "admitted_not_delivered"})
        # Wrong UID has the *same* shared-group filesystem access, but its
        # SO_PEERCRED is not allowlisted by the broker.
        self.query_as(WRONG_UID, {"op": "admit", **dict(envelope, conversation_id="chat-C",
                                                        message_id="m2")},
                      expect_success=False)
        self.assertEqual(self.query_as(UI_UID, {"op": "status"})["outstanding"], 1)
        self.assertEqual(self.query_as(UI_UID, {"op": "begin_click", **envelope}),
                         {"state": "click_started_uncertain"})
        self.stop_server()
        self.start_server()
        self.assertEqual(self.query_as(UI_UID, {"op": "admit", **envelope})["reason"],
                         "outstanding_attempt")
        self.assertEqual(self.query_as(UI_UID, {"op": "status"})["outstanding"], 1)


if __name__ == "__main__":
    unittest.main()
