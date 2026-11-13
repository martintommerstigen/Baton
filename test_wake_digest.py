"""Fail-closed body-integrity tests for synthetic existing-chat DOM.

These are NOT live ChatGPT observations. A marker without its authorized body
must never count as a delivered wake, even during crash reconciliation.
"""
import hashlib
import tempfile
import unittest

from chatgpt_ui_driver import ChatGPTUIDriver, is_marked_user_turn, marker_for
from test_wake_browser_integration import A, B, Page, Turn
from wake_adapter import reconcile
from wake_contract import WakeLedger


class BodyDigestTests(unittest.TestCase):
    def test_marker_alone_does_not_bind_body(self):
        marker = marker_for("m1")
        approved = hashlib.sha256(b"approved").hexdigest()
        self.assertTrue(is_marked_user_turn(marker + "\napproved", marker, approved))
        self.assertFalse(is_marked_user_turn(marker + "\nsubstituted", marker, approved))
        self.assertFalse(is_marked_user_turn("quoted " + marker + "\napproved", marker, approved))
        self.assertFalse(is_marked_user_turn(marker + "\napproved", marker, "wrong-digest"))

    def test_no_newline_normalization_in_digest(self):
        marker = marker_for("m1")
        digest = hashlib.sha256("alpha\nbeta".encode()).hexdigest()
        self.assertTrue(is_marked_user_turn(marker + "\nalpha\nbeta", marker, digest))
        # A CRLF, Unicode line separator, or trailing newline is a different
        # payload. splitlines() used to normalize these into false positives.
        self.assertFalse(is_marked_user_turn(marker + "\nalpha\r\nbeta", marker, digest))
        self.assertFalse(is_marked_user_turn(marker + "\nalpha\u2028beta", marker, digest))
        self.assertFalse(is_marked_user_turn(marker + "\nalpha\nbeta\n", marker, digest))
        self.assertFalse(is_marked_user_turn(marker + "\r\nalpha\nbeta", marker, digest))

    def test_trailing_newline_is_valid_only_when_approved(self):
        marker = marker_for("m2")
        body = "approved\n"
        digest = hashlib.sha256(body.encode()).hexdigest()
        self.assertTrue(is_marked_user_turn(marker + "\n" + body, marker, digest))
        self.assertFalse(is_marked_user_turn(marker + "\napproved", marker, digest))

    def test_read_only_reconciliation_rejects_wrong_body(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = WakeLedger(tmp + "/db")
            approved = "Send a harmless challenge to B"
            digest = hashlib.sha256(approved.encode("utf-8")).hexdigest()
            ledger.request("m1", A, B, digest, "source-a-turn")
            self.assertTrue(ledger.begin_submission("m1"))
            self.assertTrue(ledger.mark_uncertain("m1"))
            page = Page(B)
            page.turns = [
                Turn("user", marker_for("m1") + "\nUNRELATED"),
                Turn("assistant", "unrelated answer", "old-assistant-turn"),
            ]
            driver = ChatGPTUIDriver(page, frozenset({B}))
            self.assertEqual(reconcile(ledger, driver, "m1"), "uncertain")
            self.assertIsNone(ledger.state("m1")[2])
            self.assertEqual(page.send_count, 0)
            page.turns[0].text = marker_for("m1") + "\n" + approved
            self.assertEqual(reconcile(ledger, driver, "m1"), "verified")
            self.assertEqual(ledger.state("m1")[2], "old-assistant-turn")
            self.assertEqual(page.send_count, 0)

    def test_duplicate_matching_marker_fails_closed(self):
        page = Page(B)
        body = "approved"
        digest = hashlib.sha256(body.encode()).hexdigest()
        page.turns = [
            Turn("user", marker_for("m1") + "\n" + body),
            Turn("assistant", "reply one", "turn-one"),
            Turn("user", marker_for("m1") + "\n" + body),
            Turn("assistant", "reply two", "turn-two"),
        ]
        driver = ChatGPTUIDriver(page, frozenset({B}))
        self.assertIsNone(driver.observe_reply(B, "m1", digest))


if __name__ == "__main__":
    unittest.main()
