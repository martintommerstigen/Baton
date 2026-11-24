from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from install_baton_app import install_entry


class BatonDesktopEntryTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.launcher = self.root / "run_baton_direct.sh"
        self.launcher.write_text("#!/usr/bin/bash\nexit 0\n", encoding="utf-8")
        self.entry = self.root / "applications" / "baton.desktop"

    def test_install_is_idempotent_and_points_to_unified_app(self):
        self.assertEqual(install_entry(self.entry, self.launcher), "installed")
        text = self.entry.read_text(encoding="utf-8")
        self.assertIn("Name=Baton", text)
        self.assertIn("Exec=\"/usr/bin/bash\" \"", text)
        self.assertIn(str(self.launcher), text)
        self.assertIn("Terminal=false", text)
        self.assertEqual(install_entry(self.entry, self.launcher), "already-installed")

    def test_reject_entry_symlink(self):
        self.entry.parent.mkdir()
        outside = self.root / "outside.desktop"
        outside.write_text("Safe\n", encoding="utf-8")
        self.entry.symlink_to(outside)
        with self.assertRaisesRegex(ValueError, "symlink"):
            install_entry(self.entry, self.launcher)
        self.assertEqual(outside.read_text(), "Safe\n")

    def test_does_not_overwrite_unrelated_entry(self):
        self.entry.parent.mkdir()
        old = "[Desktop Entry]\nName=Other Tool\n"
        self.entry.write_text(old)
        with self.assertRaisesRegex(ValueError, "differs"):
            install_entry(self.entry, self.launcher)
        self.assertEqual(self.entry.read_text(), old)


if __name__ == "__main__":
    unittest.main()
