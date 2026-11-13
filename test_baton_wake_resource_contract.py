"""Negative contract tests: two resource models for Baton's idle-wake pilot.

Run against a CURRENT inspected Baton source checkout:
    BATON_IDLE_WAKE_SOURCE=/absolute/checkout python3 -m unittest -v test_baton_wake_resource_contract

These tests intentionally fail against the 2026-11-13 singleton watcher.
They modify only temporary SQLite databases. No UI/CDP, production journal,
historical queue, external contact, or wake is invoked.

This is a falsification artifact, not a live scheduler fix.
"""
import asyncio
from contextlib import nullcontext
import os
from pathlib import Path
import sys
import tempfile
import unittest

SOURCE = os.environ.get("BATON_IDLE_WAKE_SOURCE")
if SOURCE:
    if not Path(SOURCE, "baton_idle_wake.py").is_file():
        raise RuntimeError("BATON_IDLE_WAKE_SOURCE must contain baton_idle_wake.py")
    sys.path.insert(0, SOURCE)

A = "6aef3ac4-86bc-83ed-a4df-89e947bc5a34"
C = "6aef828e-0150-83eb-bbac-061f79a8fd4a"


@unittest.skipUnless(SOURCE, "Set BATON_IDLE_WAKE_SOURCE to an inspected Baton checkout")
class ResourceContract(unittest.TestCase):
    def setUp(self):
        from baton_idle_wake import Journal, Watchdog
        from baton_discussion_links import Discussion

        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.now = 1000
        discussion = Discussion(root / "topics.sqlite3", clock=lambda: self.now)
        discussion.init()
        discussion.thread("continuity-rhythm", "Resource isolation test")
        discussion.write("continuity-rhythm", A, "source-run", "source observation")
        self.journal = Journal(root / "wake.sqlite3")
        self.ui = FakeResourceUI()
        config = {
            "enabled": True,
            "idle_seconds": 60,
            "cooldown_seconds": 60,
            "owner_scope": "explicit isolated test",
            "endpoint": "http://127.0.0.1:9335",
            "targets": [
                {"chat_id": A, "title": "Spire"},
                {"chat_id": C, "title": "Siv"},
            ],
            "activity_db": str(discussion.path),
            "topic": "continuity-rhythm",
            "thread_link": "baton://local/test-only",
            "reader": "/no-real-reader",
        }
        self.watchdog = Watchdog(config, self.journal, self.ui,
                                 clock=lambda: self.now, boot=1000)
        self.pending_a = self.journal.reserve("episode-A", A, "Spire",
                                             "unresolved message A", 1000)
        self.assertIsNotNone(self.pending_a)
        self.journal.update(self.pending_a, "visible", 1000,
                            "source-bound user turn visible; no reply proof")
        self.now = 1061

    def tick(self):
        return asyncio.run(self.watchdog.tick())

    def test_two_independent_browsers_allow_C_without_resending_A(self):
        """A visible unresolved wake must not globally veto an independent C."""
        self.ui.browser_of = {A: "browser-1", C: "browser-2"}
        self.ui.busy_browsers = {"browser-1"}
        result = self.tick()
        self.assertEqual([C], self.ui.sends,
                         "C should be considered on independent idle browser")
        self.assertNotIn(A, self.ui.sends, "no replay of unresolved A")
        self.assertEqual(C, result.get("target"))

    def test_shared_busy_browser_defers_C_without_touching_A(self):
        """Shared busy browser should produce an explicit resource deferral."""
        self.ui.browser_of = {A: "browser-1", C: "browser-1"}
        self.ui.busy_browsers = {"browser-1"}
        result = self.tick()
        self.assertEqual([], self.ui.sends)
        self.assertEqual("deferred_by_browser_resource", result.get("event"))
        self.assertEqual(0, self.ui.target_preflights,
                         "do not navigate while shared browser busy")

        # Freeing the physical browser changes the permissible next action;
        # A's unresolved delivery remains in the journal.
        self.ui.busy_browsers.clear()
        self.now = 1200
        next_result = self.tick()
        self.assertEqual([C], self.ui.sends)
        self.assertEqual(C, next_result.get("target"))
        self.assertIsNotNone(self.journal.pending())

    def test_independent_C_reservation_does_not_erase_unresolved_A(self):
        """The journal must support independent pending recipients."""
        second = self.journal.reserve("episode-C", C, "Siv",
                                      "independent new invitation", 1061)
        self.assertIsNotNone(second, "global pending blocks another recipient")
        self.assertNotEqual(second, self.pending_a)
        # Need per-ID retention of A and C, rather than only one global 'pending'.
        with self.journal.db() as db:
            rows = db.execute("SELECT id,target,state FROM wakes ORDER BY id").fetchall()
        self.assertEqual({A, C}, {row["target"] for row in rows})
        self.assertEqual("visible",
                         next(row["state"] for row in rows if row["target"] == A))


class FakeResourceUI:
    """No shell, real browser or network; purely records intended operations."""
    def __init__(self):
        self.browser_of = {}
        self.busy_browsers = set()
        self.sends = []
        self.target_preflights = 0
        self.observations = 0

    def lock(self):
        return nullcontext()

    async def preflight(self, target, manual=False):
        self.target_preflights += 1
        browser = self.browser_of.get(target["chat_id"], "browser-1")
        if browser in self.busy_browsers:
            raise RuntimeError("shared browser busy; no safe navigation")
        return {"url": "https://chatgpt.com/c/" + target["chat_id"]}

    async def send(self, target, observed, text):
        self.sends.append(target["chat_id"])
        return {"state": "visible", "detail": "synthetic local visible"}

    async def observe(self, row):
        self.observations += 1
        return {"state": "visible", "detail": "A still visibly unresolved"}


if __name__ == "__main__":
    unittest.main()