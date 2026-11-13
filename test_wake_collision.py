"""Synthetic DOM regressions for preexisting marker collisions.

A previously existing user marker + assistant reply is NOT evidence that
the current wake attempt sent anything. This is not a live ChatGPT test.
"""
import hashlib
import tempfile
import unittest

from chatgpt_ui_driver import ChatGPTUIDriver, marker_for
from test_wake_browser_integration import A, B, Page, Turn
from wake_adapter import PreexistingWakeMarker, reconcile, wake_once
from wake_contract import WakeLedger


class CollisionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = WakeLedger(self.tmp.name + "/db")
        self.body = "harmless approved body"
        self.digest = hashlib.sha256(self.body.encode("utf-8")).hexdigest()
        self.page = Page(B)
        self.driver = ChatGPTUIDriver(self.page, frozenset({B}))

    def tearDown(self):
        self.tmp.cleanup()

    def test_old_identical_marker_and_reply_cannot_verify_new_attempt(self):
        self.page.turns = [
            Turn("user", marker_for("collision-1") + "\n" + self.body),
            Turn("assistant", "old reply", "old-turn"),
        ]
        with self.assertRaises(PreexistingWakeMarker):
            wake_once(self.ledger, self.driver, "collision-1", A, B,
                      self.digest, self.body, "a-origin")
        self.assertEqual(self.ledger.state("collision-1")[1], "collision")
        self.assertIsNone(self.ledger.state("collision-1")[2])
        self.assertEqual(self.page.send_count, 0)
        self.assertEqual(reconcile(self.ledger, self.driver, "collision-1"), "collision")
        self.assertEqual(wake_once(self.ledger, self.driver, "collision-1",
                                   A, B, self.digest, self.body, "a-origin"), "collision")
        self.assertEqual(self.page.send_count, 0)
        with self.assertRaises(ValueError):
            self.ledger.verify("collision-1", B, "old-turn")

    def test_collision_survives_restart(self):
        self.page.turns = [Turn("user", "quoted " + marker_for("collision-2"))]
        with self.assertRaises(PreexistingWakeMarker):
            wake_once(self.ledger, self.driver, "collision-2", A, B,
                      self.digest, self.body)
        fresh = WakeLedger(self.tmp.name + "/db")
        self.assertEqual(fresh.state("collision-2")[1], "collision")
        self.assertEqual(reconcile(fresh, self.driver, "collision-2"), "collision")
        self.assertEqual(self.page.send_count, 0)

    def test_crash_after_real_send_remains_reconcilable(self):
        self.ledger.request("actual-1", A, B, self.digest, "a-origin")
        self.ledger.begin_submission("actual-1")
        self.ledger.mark_uncertain("actual-1")
        self.page.turns = [
            Turn("user", marker_for("actual-1") + "\n" + self.body),
            Turn("assistant", "real reply", "actual-turn"),
        ]
        self.assertEqual(reconcile(self.ledger, self.driver, "actual-1"), "verified")
        self.assertEqual(self.ledger.state("actual-1")[2], "actual-turn")
        self.assertEqual(self.page.send_count, 0)

    def test_duplicate_marker_with_different_body_is_ambiguous(self):
        self.page.turns = [
            Turn("user", marker_for("mixed-1") + "\nWRONG BODY"),
            Turn("assistant", "old reply", "old-turn"),
            Turn("user", marker_for("mixed-1") + "\n" + self.body),
            Turn("assistant", "new reply", "new-turn"),
        ]
        self.assertIsNone(self.driver.observe_reply(B, "mixed-1", self.digest))


if __name__ == "__main__":
    unittest.main()
