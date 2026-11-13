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
                execute("git-revision", d)

    def test_workspace_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            real = root / "real"
            real.mkdir()
            (root / "alias").symlink_to(real, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "symlink"):
                execute("identity", root / "alias")

    def test_git_metadata_file_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / ".git").write_text("gitdir: /tmp/elsewhere")
            with self.assertRaisesRegex(ValueError, "metadata"):
                execute("git-revision", d)

if __name__ == "__main__":
    unittest.main()
