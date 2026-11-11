"""B5/B2 create-only desktop installer negative controls; disposable filesystem."""
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

from remote_security.desktop_install_guard import install, UnsafeInstallation, NAME


class GuardTests(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.addCleanup(self.t.cleanup)
        self.root = Path(self.t.name)
        self.client = self.root / "client.py"
        self.client.write_text("print('local')\n")
        self.target = self.root / "safe" / "applications"

    def call(self, dest=None):
        return install(str(self.client), str(dest or self.target))

    def test_install_is_valid_and_create_only(self):
        path = Path(self.call())
        self.assertEqual(path.name, NAME)
        self.assertIn("--help", path.read_text())
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o644)
        with self.assertRaises(UnsafeInstallation):
            self.call()
        self.assertIn("--help", path.read_text())

    def test_existing_file_preserved(self):
        self.target.mkdir(parents=True)
        dest = self.target / NAME
        dest.write_text("preexisting user data")
        with self.assertRaises(UnsafeInstallation):
            self.call()
        self.assertEqual(dest.read_text(), "preexisting user data")

    def test_existing_symlink_preserved(self):
        self.target.mkdir(parents=True)
        other = self.root / "valuable"
        other.write_text("keep")
        (self.target / NAME).symlink_to(other)
        with self.assertRaises(UnsafeInstallation):
            self.call()
        self.assertEqual(other.read_text(), "keep")

    def test_parent_symlink_rejected(self):
        real = self.root / "real"
        real.mkdir()
        alias = self.root / "alias"
        alias.symlink_to(real, target_is_directory=True)
        with self.assertRaises((UnsafeInstallation, OSError)):
            self.call(alias / "applications")
        self.assertFalse((real / "applications").exists())

    def test_parent_group_writable_rejected(self):
        self.target.mkdir(parents=True)
        os.chmod(self.target.parent, 0o777)
        with self.assertRaises(UnsafeInstallation):
            self.call()
        self.assertFalse((self.target / NAME).exists())

    def test_dotdot_rejected(self):
        with self.assertRaises(UnsafeInstallation):
            self.call(str(self.root / "safe/../other"))

    def test_missing_client_rejected(self):
        self.client.unlink()
        with self.assertRaises(UnsafeInstallation):
            self.call()

    def test_wrong_client_name_rejected(self):
        other = self.root / "evil.py"
        other.write_text("pass")
        with self.assertRaises(UnsafeInstallation):
            install(str(other), str(self.target))

    def test_parent_replaced_during_publish_rejected_and_rolled_back(self):
        self.target.mkdir(parents=True)
        moved = self.root / "moved"
        real_link = os.link
        def swap(src, dst, **kwargs):
            self.target.rename(moved)
            self.target.mkdir()
            return real_link(src, dst, **kwargs)
        with patch("remote_security.desktop_install_guard.os.link", side_effect=swap):
            with self.assertRaises(UnsafeInstallation):
                self.call()
        self.assertFalse((self.target / NAME).exists())
        self.assertFalse((moved / NAME).exists())

    def test_temp_no_leftovers(self):
        self.call()
        self.assertEqual([p.name for p in self.target.iterdir()], [NAME])

    def test_preexisting_fifo_preserved(self):
        self.target.mkdir(parents=True)
        os.mkfifo(self.target / NAME)
        with self.assertRaises(UnsafeInstallation):
            self.call()
        self.assertTrue(stat.S_ISFIFO((self.target / NAME).lstat().st_mode))

    def test_root_or_setuid_execution_rejected(self):
        with patch("remote_security.desktop_install_guard.os.geteuid", return_value=0):
            with self.assertRaises(UnsafeInstallation):
                self.call()
        with patch("remote_security.desktop_install_guard.os.geteuid", return_value=1234), patch("remote_security.desktop_install_guard.os.getuid", return_value=4321):
            with self.assertRaises(UnsafeInstallation):
                self.call()

    def test_two_concurrent_publishers_one_wins(self):
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(self.call) for _ in range(2)]
            results = []
            for f in futures:
                try:
                    results.append(f.result())
                except UnsafeInstallation:
                    results.append("rejected")
        self.assertEqual(results.count("rejected"), 1)
        self.assertTrue((self.target / NAME).is_file())


if __name__ == "__main__":
    unittest.main()
