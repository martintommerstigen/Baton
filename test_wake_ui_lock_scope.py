"""B1 lock-scope regressions, motivated by Riss R20's 7 Nov Greg deadlock.

No ChatGPT UI, broker, Greg or model worker is contacted.
"""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from wake_ui_lock import LockingUIDriver, ui_controller_lock


class FakeDriver:
    def __init__(self):
        self.submits = 0
        self.observations = 0
        self.on_submit = None
        self.on_observe = None

    def submit_once(self, *args, **kwargs):
        self.submits += 1
        if self.on_submit:
            self.on_submit()
        return "synthetic_clicked"

    def observe_reply(self, *args):
        self.observations += 1
        if self.on_observe:
            self.on_observe()
        return "synthetic_reply"

    def read_assistant_turn(self, *args):
        return "read_only_source"


class ShortUILockTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / "ui" / "lock"
        self.base = FakeDriver()
        self.driver = LockingUIDriver(self.base, self.path)

    def other_process_can_enter(self):
        code = (
            "import sys\n"
            "from wake_ui_lock import ui_controller_lock\n"
            "try:\n"
            " with ui_controller_lock(sys.argv[1]): sys.exit(3)\n"
            "except RuntimeError: sys.exit(0)\n"
        )
        p = subprocess.run(
            [sys.executable, "-c", code, str(self.path)],
            cwd=str(Path(__file__).parent), capture_output=True,
            text=True, timeout=5,
        )
        return p.returncode

    def test_lock_held_during_exact_submission_and_broker_callback(self):
        self.base.on_submit = lambda: self.assertEqual(self.other_process_can_enter(), 0)
        self.assertEqual(self.driver.submit_once("B", "m1", "body"), "synthetic_clicked")
        self.assertEqual(self.base.submits, 1)

    def test_lock_released_before_observation_and_other_chat_can_act(self):
        self.base.on_observe = lambda: self.assertEqual(self.other_process_can_enter(), 3)
        self.driver.submit_once("B", "m1", "body")
        self.assertEqual(self.driver.observe_reply("B", "m1", "digest"), "synthetic_reply")
        self.assertEqual(self.base.observations, 1)
        self.assertEqual(self.driver.read_assistant_turn("B", "turn"), "read_only_source")

    def test_competing_writer_cannot_click(self):
        with ui_controller_lock(self.path):
            with self.assertRaises(RuntimeError):
                self.driver.submit_once("B", "m1", "body")
        self.assertEqual(self.base.submits, 0)

    def test_exception_releases_lock_and_no_hidden_retry(self):
        def failure():
            raise RuntimeError("synthetic uncertain after click start")
        self.base.on_submit = failure
        with self.assertRaisesRegex(RuntimeError, "synthetic uncertain"):
            self.driver.submit_once("B", "m1", "body")
        self.assertEqual(self.base.submits, 1)
        self.assertEqual(self.other_process_can_enter(), 3)
        self.assertEqual(self.base.submits, 1)

    def test_verified_entrypoints_wrap_the_target_not_entire_wait(self):
        from pathlib import Path
        root = Path(__file__).parent
        for name in ("run_verified_broker_wake.py", "run_verified_broker_chain.py"):
            with self.subTest(name=name):
                src = (root / name).read_text()
                self.assertIn("LockingUIDriver(ChatGPTUIDriver(", src)
                self.assertNotIn("with ui_controller_lock(), sync_playwright()", src)


if __name__ == "__main__":
    unittest.main()
