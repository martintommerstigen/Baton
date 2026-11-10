"""B1/B5 launcher filesystem security negatives (Kubuntu/Linux, no network)."""
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1] / "desktop" / "install_baton_launcher.py"
spec = importlib.util.spec_from_file_location("baton_launcher_security", SOURCE)
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


class LauncherFilesystemSecurityTests(unittest.TestCase):
    def make_client(self, root):
        client = root / "client.py"
        client.write_text("", encoding="utf-8")
        return client

    def test_symlinked_parent_does_not_redirect_install(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            client = self.make_client(root)
            actual = root / "actual"
            actual.mkdir()
            (root / "redirect").symlink_to(actual, target_is_directory=True)
            with self.assertRaises(OSError):
                launcher.install(client, root / "redirect" / "baton.desktop")
            self.assertFalse((actual / "baton.desktop").exists())

    def test_shared_writable_directory_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            client = self.make_client(root)
            shared = root / "shared"
            shared.mkdir()
            shared.chmod(0o777)
            with self.assertRaises(PermissionError):
                launcher.install(client, shared / "baton.desktop")
            self.assertFalse((shared / "baton.desktop").exists())

    def test_repeat_install_is_atomic_and_leaves_no_temporary_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            client = self.make_client(root)
            dest = root / "baton.desktop"
            launcher.install(client, dest)
            before = dest.read_bytes()
            launcher.install(client, dest)
            self.assertEqual(before, dest.read_bytes())
            self.assertEqual(dest.stat().st_mode & 0o777, 0o644)
            self.assertEqual(sorted(p.name for p in root.iterdir()), ["baton.desktop", "client.py"])

    def test_fifo_destination_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            client = self.make_client(root)
            dest = root / "baton.desktop"
            os.mkfifo(dest)
            with self.assertRaises(ValueError):
                launcher.install(client, dest)


if __name__ == "__main__":
    unittest.main()
