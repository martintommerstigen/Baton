"""Proven pre-click rejection vs uncertain post-click delivery.

Synthetic DOM only: does not prove the live ChatGPT selectors or a real wake.
"""
import hashlib
import tempfile
import unittest
from unittest.mock import patch

from chatgpt_ui_driver import ChatGPTUIDriver
from test_wake_browser_integration import A, B, Page
from wake_adapter import PreSubmissionRejected, reconcile, wake_once
from wake_contract import WakeLedger


class PreSendAbortTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = WakeLedger(self.tmp.name + "/db")
        self.page = Page(B)
        self.driver = ChatGPTUIDriver(self.page, frozenset({B}))
        self.body = "harmless"
        self.digest = hashlib.sha256(self.body.encode("utf-8")).hexdigest()

    def tearDown(self):
        self.tmp.cleanup()

    def wake(self, mid, driver=None):
        return wake_once(self.ledger, driver or self.driver, mid, A, B,
                         self.digest, self.body)

    def test_pause_before_click_aborts_and_frees_target(self):
        with patch("chatgpt_ui_driver.PAUSE_FILE") as pause:
            pause.exists.return_value = True
            with self.assertRaisesRegex(PreSubmissionRejected, "paused"):
                self.wake("paused-1")
        self.assertEqual(self.page.send_count, 0)
        self.assertEqual(self.ledger.state("paused-1")[1], "aborted")
        self.assertEqual(reconcile(self.ledger, self.driver, "paused-1"), "aborted")
        self.assertEqual(self.wake("paused-1"), "aborted")
        self.assertEqual(self.page.send_count, 0)
        with patch("chatgpt_ui_driver.PAUSE_FILE") as pause:
            pause.exists.return_value = False
            self.assertEqual(self.wake("after-pause"), "verified")
        self.assertEqual(self.page.send_count, 1)

    def test_existing_draft_aborts_without_modifying_draft(self):
        self.page.composer.text = "user's unsent draft"
        with self.assertRaisesRegex(PreSubmissionRejected, "draft"):
            self.wake("draft-1")
        self.assertEqual(self.page.composer.text, "user's unsent draft")
        self.assertEqual(self.page.send_count, 0)
        self.assertEqual(self.ledger.state("draft-1")[1], "aborted")
        self.page.composer.text = ""
        with patch("chatgpt_ui_driver.PAUSE_FILE") as pause:
            pause.exists.return_value = False
            self.assertEqual(self.wake("draft-cleared"), "verified")
        self.assertEqual(self.page.send_count, 1)

    def test_mutated_composer_aborts_without_send(self):
        def normalized_fill(value):
            self.page.composer.text = value.replace("\n", " ")
        self.page.composer.fill = normalized_fill
        with patch("chatgpt_ui_driver.PAUSE_FILE") as pause:
            pause.exists.return_value = False
            with self.assertRaisesRegex(PreSubmissionRejected, "differs"):
                self.wake("mutated-1")
        self.assertEqual(self.page.send_count, 0)
        self.assertEqual(self.ledger.state("mutated-1")[1], "aborted")
        with self.assertRaises(ValueError):
            self.ledger.verify("mutated-1", B, "invented-turn")

    def test_post_click_exception_stays_uncertain_and_blocks_replay(self):
        class PostClickFailure:
            def __init__(self, driver):
                self.driver = driver
            def submit_once(self, *args):
                self.driver.submit_once(*args)
                raise RuntimeError("connection lost AFTER Send click")
            def observe_reply(self, *args):
                return self.driver.observe_reply(*args)

        with patch("chatgpt_ui_driver.PAUSE_FILE") as pause:
            pause.exists.return_value = False
            with self.assertRaisesRegex(RuntimeError, "AFTER Send"):
                self.wake("clicked-1", PostClickFailure(self.driver))
        self.assertEqual(self.page.send_count, 1)
        self.assertEqual(self.ledger.state("clicked-1")[1], "uncertain")
        with self.assertRaisesRegex(RuntimeError, "unresolved wake"):
            self.wake("blocked-2")
        self.assertEqual(self.page.send_count, 1)
        self.assertEqual(reconcile(self.ledger, self.driver, "clicked-1"), "verified")
        with patch("chatgpt_ui_driver.PAUSE_FILE") as pause:
            pause.exists.return_value = False
            self.assertEqual(self.wake("after-reconcile"), "verified")
        self.assertEqual(self.page.send_count, 2)

    def test_terminal_aborted_is_not_reconcilable_or_verifiable(self):
        self.ledger.request("terminal", A, B, self.digest)
        self.assertTrue(self.ledger.begin_submission("terminal"))
        self.assertTrue(self.ledger.mark_aborted("terminal"))
        self.assertFalse(self.ledger.mark_aborted("terminal"))
        self.assertEqual(reconcile(self.ledger, self.driver, "terminal"), "aborted")
        with self.assertRaises(ValueError):
            self.ledger.verify("terminal", B, "old-turn")


if __name__ == "__main__":
    unittest.main()
