"""Negative and smoke tests for local Baton terminal adapter."""
import tempfile
from pathlib import Path
import unittest
from baton_local_terminal import execute

class LocalTerminalTests(unittest.TestCase):
    def test_identity_and_python(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertTrue(execute("identity", d)["ok"])
            self.assertTrue(execute("python-version", d)["ok"])
    def test_arbitrary_shell_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                execute("sh -c id", d)
    def test_nonexistent_workspace_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(FileNotFoundError):
                execute("identity", str(Path(d) / "missing"))
    def test_git_requires_checkout(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                execute("git-status", d)

if __name__ == "__main__":
    unittest.main()
