"""B1/B5 H20: real Linux four-role AF_UNIX + Ronja R21 integration.

Root-only disposable GitHub CI. Numeric UIDs, no accounts, no browser, no
network, no tokens. A kernel UID is NOT an existing ChatGPT assistant turn.
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

try:
    from remote_security.admission_sender_scope import (
        AuthenticatedAdmissionProxy, SenderScopePolicy,
    )
except ImportError:
    if os.environ.get("B1_REQUIRE_R21") == "1":
        raise
    AuthenticatedAdmissionProxy = SenderScopePolicy = None

SERVICE = 61001
SENDER_A = 61002
SENDER_B = 61003
CONTROLLER = 61004
WRONG = 61005
GROUP = 61006


@unittest.skipUnless(os.geteuid() == 0 and hasattr(socket, "SO_PEERCRED")
                     and SenderScopePolicy is not None,
                     "Linux root-only integration with pinned R21 source")
class RealScopedUIDTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.root.chmod(0o711)
        self.shared = self.root / "shared"
        self.shared.mkdir(mode=0o710)
        os.chown(self.shared, SERVICE, GROUP)
        self.shared.chmod(0o710)
        self.private = self.root / "private"
        self.private.mkdir(mode=0o700)
        os.chown(self.private, SERVICE, SERVICE)
        self.private.chmod(0o700)
        self.sock = self.shared / "admission.sock"
        self.db = self.private / "admissions.sqlite"
        self.pause = self.private / "PAUSE_UI_WRITES"
        self.pid = None
        self.addCleanup(self.stop_server)

    def start_server(self):
        pid = os.fork()
        if pid == 0:
            try:
                os.setgroups([GROUP])
                os.setgid(SERVICE)
                os.setuid(SERVICE)
                inner = AdmissionStore(self.db, self.pause, {"chat-B", "chat-C"})
                policy = SenderScopePolicy(
                    broker_uid=SERVICE, controller_uid=CONTROLLER,
                    sender_uids={SENDER_A: "chat-A", SENDER_B: "chat-B"},
                    allowed_targets={"chat-B", "chat-C"},
                    sender_routes={"chat-A": {"chat-B"}, "chat-B": {"chat-C"}},
                )
                proxy = AuthenticatedAdmissionProxy(inner, policy)
                with Broker(self.sock, proxy,
                            [SENDER_A, SENDER_B, CONTROLLER, WRONG],
                            shared_gid=GROUP) as server:
                    server.serve_forever(poll_interval=0.01)
            except BaseException:
                os._exit(111)
            os._exit(0)
        self.pid = pid
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            done, status = os.waitpid(pid, os.WNOHANG)
            if done:
                self.pid = None
                self.fail(f"scoped broker died before bind: {status}")
            if self.sock.exists():
                st = self.sock.stat()
                if stat.S_ISSOCK(st.st_mode) and stat.S_IMODE(st.st_mode) == 0o660:
                    self.assertEqual((st.st_uid, st.st_gid), (SERVICE, GROUP))
                    return
            time.sleep(0.02)
        self.fail("scoped broker did not bind")

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
        # Test harness only; never auto-unlink a production unknown socket.
        self.sock.unlink(missing_ok=True)

    def query_as(self, uid, request):
        frame = (json.dumps(request, sort_keys=True) + "\n").encode("utf-8")
        code = (
            "import json,socket; s=socket.socket(socket.AF_UNIX); "
            "s.connect(" + repr(str(self.sock)) + "); "
            "s.sendall(" + repr(frame) + "); "
            "s.shutdown(socket.SHUT_WR); "
            "data=s.recv(8192); s.close(); print(json.dumps(json.loads(data)))"
        )
        def drop():
            os.setgroups([GROUP])
            os.setgid(uid)
            os.setuid(uid)
        proc = subprocess.run(
            [sys.executable, "-c", code], preexec_fn=drop,
            capture_output=True, text=True, timeout=7)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return json.loads(proc.stdout)

    @staticmethod
    def envelope(sender="chat-A", target="chat-B", message="m1", turn="turn-A"):
        return {
            "conversation_id": target, "message_id": message,
            "origin_turn_id": turn, "sender_id": sender,
            "payload_sha256": "a" * 64,
        }

    def test_real_uid_scope_admit_begin_restart_and_no_blind_retry(self):
        self.start_server()
        a = self.envelope()
        self.assertEqual(self.query_as(CONTROLLER, {"op": "admit", **a})["reason"],
                         "sender_uid_mismatch")
        self.assertEqual(self.query_as(SENDER_B, {"op": "admit", **a})["reason"],
                         "sender_uid_mismatch")
        self.assertEqual(self.query_as(SENDER_A, {"op": "admit",
                        **self.envelope(target="chat-C")})["reason"],
                         "sender_target_route_denied")
        self.assertEqual(self.query_as(WRONG, {"op": "admit", **a})["reason"],
                         "sender_uid_mismatch")
        self.assertEqual(self.query_as(SENDER_A, {"op": "admit", **a})["state"],
                         "admitted_not_delivered")
        self.assertEqual(self.query_as(SENDER_A, {"op": "begin_click", **a})["reason"],
                         "controller_only")
        self.assertEqual(self.query_as(CONTROLLER, {"op": "begin_click", **a})["state"],
                         "click_started_uncertain")
        self.stop_server()
        self.start_server()
        self.assertEqual(self.query_as(SENDER_A, {"op": "admit", **a})["reason"],
                         "outstanding_attempt")
        self.assertEqual(self.query_as(CONTROLLER, {"op": "status"})["outstanding"], 1)
        # A new B→C is still only a kernel-UID-scoped *claim*.
        b = self.envelope(sender="chat-B", target="chat-C",
                          message="m2", turn="turn-B")
        self.assertEqual(self.query_as(SENDER_B, {"op": "admit", **b})["state"],
                         "admitted_not_delivered")
        self.pause.touch()
        self.assertEqual(self.query_as(CONTROLLER, {"op": "begin_click", **b})["reason"],
                         "paused_or_untrusted")


if __name__ == "__main__":
    unittest.main()
