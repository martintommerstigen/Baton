"""Synthetic host-lock tests; no live ChatGPT UI is contacted."""
import ast
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from wake_ui_lock import ui_controller_lock


class HostLockTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "baton" / "chatgpt-ui.lock"

    def tearDown(self):
        self.tmp.cleanup()

    def child_exit(self):
        script = ("import sys\nfrom wake_ui_lock import ui_controller_lock\n"
                  "try:\n"
                  "    with ui_controller_lock(sys.argv[1]): sys.exit(2)\n"
                  "except RuntimeError: sys.exit(0)\n")
        return subprocess.run([sys.executable, "-c", script, str(self.path)],
                              cwd=str(Path(__file__).parent), timeout=5,
                              capture_output=True, text=True)

    def test_both_ui_entrypoints_use_shared_lock_context(self):
        for name in ("run_chatgpt_wake.py", "run_chatgpt_wake_chain.py"):
            with self.subTest(name=name):
                source = (Path(__file__).parent / name).read_text()
                tree = ast.parse(source)
                self.assertTrue(any(
                    isinstance(node, ast.With) and any(
                        isinstance(item.context_expr, ast.Call)
                        and isinstance(item.context_expr.func, ast.Name)
                        and item.context_expr.func.id == "ui_controller_lock"
                        for item in node.items)
                    for node in ast.walk(tree)), "runner must hold the shared UI lock")

    def test_separate_process_with_separate_ledger_cannot_enter(self):
        with ui_controller_lock(self.path):
            result = self.child_exit()
            self.assertEqual(result.returncode, 0, result.stderr)
        result = self.child_exit()
        self.assertEqual(result.returncode, 2, result.stderr)

    def test_exception_releases_lock(self):
        with self.assertRaisesRegex(ValueError, "test"):
            with ui_controller_lock(self.path):
                raise ValueError("test")
        with ui_controller_lock(self.path):
            pass

    def test_symlink_lock_is_rejected(self):
        self.path.parent.mkdir(mode=0o700)
        target = self.path.parent / "other"
        target.write_text("do not touch")
        self.path.symlink_to(target)
        with self.assertRaises(OSError):
            with ui_controller_lock(self.path):
                pass
        self.assertEqual(target.read_text(), "do not touch")

    def test_insecure_lock_directory_is_rejected(self):
        self.path.parent.mkdir(mode=0o700)
        self.path.parent.chmod(0o777)
        with self.assertRaises(PermissionError):
            with ui_controller_lock(self.path):
                pass

    def test_insecure_existing_lock_file_is_rejected(self):
        self.path.parent.mkdir(mode=0o700)
        self.path.write_text("keep")
        self.path.chmod(0o666)
        with self.assertRaises(PermissionError):
            with ui_controller_lock(self.path):
                pass
        self.assertEqual(self.path.read_text(), "keep")


if __name__ == "__main__":
    unittest.main()
