"""B1/B5 H20: pinned Ronja R21 cross-branch policy integration.

Synthetic peer UID decisions over a REAL local AF_UNIX broker/SQLite path.
This is NOT a Greg/ChatGPT wake, not real cross-UID authentication, and not
evidence of an existing assistant turn. Ronja's separate privileged tests
cover kernel UID behavior; this checks the B1 handler integration boundary.
"""
import os
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest import mock

from wake_admission_broker import AdmissionStore, Broker, query

try:
    from remote_security.admission_sender_scope import (
        AuthenticatedAdmissionProxy, SenderScopePolicy,
    )
except ImportError:
    if os.environ.get("B1_REQUIRE_R21") == "1":
        raise
    AuthenticatedAdmissionProxy = SenderScopePolicy = None


@unittest.skipIf(SenderScopePolicy is None, "Pinned Ronja R21 source not installed")
class R21ScopedDispatchTests(unittest.TestCase):
    def setUp(self):
        if os.geteuid() == 0:
            self.skipTest("Unprivileged broker UID required; real-UID tests are separate")
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.store = AdmissionStore(root / "admissions.sqlite",
                                    root / "PAUSE_UI_WRITES", {"chat-B", "chat-C"})
        self.sender_a_uid = os.getuid() + 20001
        self.sender_b_uid = os.getuid() + 20002
        self.controller_uid = os.getuid() + 20003
        self.policy = SenderScopePolicy(
            broker_uid=os.geteuid(),
            controller_uid=self.controller_uid,
            sender_uids={self.sender_a_uid: "chat-A",
                         self.sender_b_uid: "chat-B"},
            allowed_targets={"chat-B", "chat-C"},
            sender_routes={"chat-A": {"chat-B"}, "chat-B": {"chat-C"}},
        )
        self.proxy = AuthenticatedAdmissionProxy(self.store, self.policy)
        self.broker = Broker(root / "broker.sock", self.proxy, [os.getuid()])
        self.thread = threading.Thread(
            target=self.broker.serve_forever,
            kwargs={"poll_interval": 0.01}, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop)

    def stop(self):
        self.broker.shutdown()
        self.thread.join(timeout=2)
        self.broker.server_close()

    def envelope(self, *, sender="chat-A", target="chat-B", message="m1"):
        return {
            "op": "admit",
            "conversation_id": target,
            "message_id": message,
            "origin_turn_id": "assistant-source-1",
            "sender_id": sender,
            "payload_sha256": "a" * 64,
        }

    def ask_as(self, uid, req):
        # Patch the R21 kernel boundary ONLY, not the broker's real UID or
        # socket. This tests dispatch and policy, not kernel authentication.
        with mock.patch("remote_security.admission_sender_scope.kernel_uid",
                        return_value=uid):
            return query(self.broker.public_path, req)

    def count(self):
        with sqlite3.connect(self.store.db_path) as db:
            return db.execute("SELECT COUNT(*) FROM admissions").fetchone()[0]

    def test_sender_a_admits_b_and_controller_begins_exact_attempt(self):
        req = self.envelope()
        self.assertEqual(self.ask_as(self.sender_a_uid, req)["state"],
                         "admitted_not_delivered")
        self.assertEqual(self.ask_as(self.sender_a_uid,
                                    {**req, "op": "begin_click"})["reason"],
                         "controller_only")
        self.assertEqual(self.ask_as(self.controller_uid,
                                    {**req, "op": "begin_click"})["state"],
                         "click_started_uncertain")
        self.assertEqual(self.ask_as(self.controller_uid,
                                    {**req, "op": "begin_click"})["state"],
                         "rejected")
        with sqlite3.connect(self.store.db_path) as db:
            self.assertEqual(db.execute(
                "SELECT state FROM admissions WHERE conversation_id='chat-B'"
            ).fetchone()[0], "uncertain")

    def test_controller_cannot_admit_even_after_claimed_ui_source_check(self):
        # B1's current run_verified_broker_wake.py invokes both operations
        # from ONE UI-controller process. That cannot satisfy R21's role split.
        result = self.ask_as(self.controller_uid, self.envelope())
        self.assertEqual(result["reason"], "sender_uid_mismatch")
        self.assertEqual(self.count(), 0)

    def test_sender_spoof_and_wrong_route_rejected_without_db_effect(self):
        self.assertEqual(
            self.ask_as(self.sender_b_uid, self.envelope())["reason"],
            "sender_uid_mismatch")
        self.assertEqual(
            self.ask_as(self.sender_a_uid,
                        self.envelope(target="chat-C"))["reason"],
            "sender_target_route_denied")
        self.assertEqual(self.count(), 0)

    def test_sender_b_to_c_is_only_uid_scoped_claim(self):
        req = self.envelope(sender="chat-B", target="chat-C", message="m2")
        self.assertEqual(self.ask_as(self.sender_b_uid, req)["state"],
                         "admitted_not_delivered")
        self.assertEqual(self.count(), 1)
        # The test deliberately does NOT claim source turn or UI delivery.

    def test_missing_kernel_credentials_rejects_and_unscoped_api_forbidden(self):
        with self.assertRaises(PermissionError):
            self.proxy.request(self.envelope())
        with mock.patch("remote_security.admission_sender_scope.kernel_uid",
                        side_effect=ValueError("not an AF_UNIX peer")):
            result = query(self.broker.public_path, self.envelope())
        self.assertEqual(result["reason"], "missing_kernel_peer")
        self.assertEqual(self.count(), 0)

    def test_pause_is_controller_only_and_persistent(self):
        self.assertEqual(
            self.ask_as(self.sender_a_uid, {"op": "pause"})["reason"],
            "controller_only")
        self.assertEqual(
            self.ask_as(self.controller_uid, {"op": "pause"})["state"],
            "pause_recorded_not_revocation")
        self.assertEqual(
            self.ask_as(self.sender_a_uid, self.envelope())["reason"],
            "paused_or_untrusted")
        self.assertEqual(self.count(), 0)


if __name__ == "__main__":
    unittest.main()
