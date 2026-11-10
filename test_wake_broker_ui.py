"""Offline B1 broker/UI boundary tests; no Greg, CDP, or ChatGPT writes."""
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from chatgpt_ui_driver import ChatGPTUIDriver
from test_chatgpt_ui_submission import CID, Page
from wake_adapter import PreSubmissionRejected
from wake_admission_broker import AdmissionStore
from wake_broker_ui import BrokerGatedUIDriver, BrokerOutcomeUncertain


class BrokerUITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.pause = root / "PAUSE_UI_WRITES"
        self.db = root / "admissions.sqlite3"
        self.store = AdmissionStore(self.db, self.pause, [CID])
        self.page = Page()
        self.ui = ChatGPTUIDriver(self.page, frozenset({CID}))
        self.patch_pause = patch("chatgpt_ui_driver.PAUSE_FILE", self.pause)
        self.patch_pause.start()
        self.addCleanup(self.patch_pause.stop)
        self.calls = []

    def broker(self, request):
        self.calls.append(request.copy())
        return self.store.request(request)

    def gated(self, request=None):
        return BrokerGatedUIDriver(self.ui, request or self.broker,
                                   sender_id="chat-A",
                                   origin_turn_id="observed-turn-A")

    def state(self):
        with self.store.connect() as db:
            row = db.execute("SELECT state FROM admissions WHERE conversation_id=?",
                             (CID,)).fetchone()
            return row[0] if row else None

    def test_exact_preflight_then_admit_begin_then_click(self):
        def checked_broker(request):
            self.assertEqual(self.page.send.clicks, 0)
            self.assertEqual(self.page.editor.inner_text(),
                             "[BATON-WAKE:msg-1]\nhello")
            return self.broker(request)
        self.gated(checked_broker).submit_once(CID, "msg-1", "hello")
        self.assertEqual([r["op"] for r in self.calls], ["admit", "begin_click"])
        self.assertEqual(self.calls[0]["payload_sha256"],
                         hashlib.sha256(b"hello").hexdigest())
        self.assertEqual(self.state(), "uncertain")
        self.assertEqual(self.page.send.clicks, 1)

    def test_draft_rejected_before_any_broker_state(self):
        self.page.editor.text = "user draft"
        with self.assertRaises(PreSubmissionRejected):
            self.gated().submit_once(CID, "msg-1", "hello")
        self.assertEqual(self.calls, [])
        self.assertIsNone(self.state())
        self.assertEqual(self.page.send.clicks, 0)

    def test_pause_before_preflight_rejects_without_admission(self):
        self.pause.write_text("paused")
        with self.assertRaises(PreSubmissionRejected):
            self.gated().submit_once(CID, "msg-1", "hello")
        self.assertEqual(self.calls, [])
        self.assertIsNone(self.state())
        self.assertEqual(self.page.send.clicks, 0)

    def test_broker_rejection_never_clicks(self):
        def reject(request):
            self.calls.append(request)
            return {"state": "rejected", "reason": "unknown"}
        with self.assertRaises(BrokerOutcomeUncertain):
            self.gated(reject).submit_once(CID, "msg-1", "hello")
        self.assertEqual(self.page.send.clicks, 0)
        self.assertEqual(len(self.calls), 1)

    def test_crash_after_committed_begin_before_click_never_retries(self):
        def crash_after_commit(request):
            answer = self.broker(request)
            if request["op"] == "begin_click":
                raise RuntimeError("simulated worker crash before click")
            return answer
        with self.assertRaises(BrokerOutcomeUncertain):
            self.gated(crash_after_commit).submit_once(CID, "msg-1", "hello")
        self.assertEqual(self.state(), "uncertain")
        self.assertEqual(self.page.send.clicks, 0)
        self.store = AdmissionStore(self.db, self.pause, [CID])  # restart
        self.page.editor.text = ""  # isolated fake UI reset; never a resend
        with self.assertRaises(BrokerOutcomeUncertain):
            self.gated().submit_once(CID, "msg-1", "hello")
        self.assertEqual(self.page.send.clicks, 0)
        self.assertEqual(self.state(), "uncertain")

    def test_crash_after_click_before_observation_never_retries(self):
        def crash_after_click():
            self.page.send.clicks += 1
            raise RuntimeError("simulated crash after click")
        self.page.send.click = crash_after_click
        with self.assertRaises(RuntimeError):
            self.gated().submit_once(CID, "msg-1", "hello")
        self.assertEqual(self.page.send.clicks, 1)
        self.assertEqual(self.state(), "uncertain")
        self.store = AdmissionStore(self.db, self.pause, [CID])
        self.page.editor.text = ""
        with self.assertRaises(BrokerOutcomeUncertain):
            self.gated().submit_once(CID, "msg-1", "hello")
        self.assertEqual(self.page.send.clicks, 1)

    def test_pause_after_durable_begin_prevents_click_but_stays_uncertain(self):
        def pause_after_begin(request):
            answer = self.broker(request)
            if request["op"] == "begin_click":
                self.pause.write_text("paused")
            return answer
        with self.assertRaisesRegex(RuntimeError, "Pause after click-start"):
            self.gated(pause_after_begin).submit_once(CID, "msg-1", "hello")
        self.assertEqual(self.state(), "uncertain")
        self.assertEqual(self.page.send.clicks, 0)

    def test_mutated_composer_after_begin_never_clicks(self):
        original_enabled = self.page.send.is_enabled
        checks = [0]
        def mutate_on_second_check():
            checks[0] += 1
            if checks[0] == 2:
                self.page.editor.text += "TAMPERED"
            return original_enabled()
        self.page.send.is_enabled = mutate_on_second_check
        with self.assertRaisesRegex(RuntimeError, "Composer changed after click-start"):
            self.gated().submit_once(CID, "msg-1", "hello")
        self.assertEqual(self.state(), "uncertain")
        self.assertEqual(self.page.send.clicks, 0)

    def test_forged_envelope_response_never_clicks(self):
        def changed_digest(request):
            request = dict(request)
            request["payload_sha256"] = "0" * 64
            return self.broker(request)
        # A malicious client changing both envelopes could still admit its
        # own digest: this test must not pretend the broker attests UI bytes.
        with self.assertRaises(AssertionError):
            self.assertEqual(self.gated(changed_digest).sender_id, "chat-B")
        self.assertIsNone(self.state())

    def test_missing_broker_callback_is_rejected(self):
        with self.assertRaises(TypeError):
            BrokerGatedUIDriver(self.ui, None, "chat-A", "observed-turn-A")


if __name__ == "__main__":
    unittest.main()
