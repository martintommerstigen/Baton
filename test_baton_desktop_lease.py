import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from baton_desktop_lease import create_ui_lease, ui_lease_active, release_ui_lease


class BatonDesktopLeaseTests(unittest.TestCase):
    def test_live_lease_and_release(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / "ui.json"
            self.assertFalse(ui_lease_active(path))
            marker = create_ui_lease(path)
            self.assertEqual(marker["pid"], os.getpid())
            self.assertTrue(ui_lease_active(path))
            self.assertEqual(path.stat().st_mode & 0o077, 0)
            release_ui_lease(marker, path)
            self.assertFalse(ui_lease_active(path))

    def test_reject_stale_process_reuse(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / "ui.json"
            marker = create_ui_lease(path)
            forged = dict(marker, start_ticks=marker["start_ticks"] + 1)
            path.write_text(json.dumps(forged))
            self.assertFalse(ui_lease_active(path))
            release_ui_lease(marker, path)
            self.assertTrue(path.exists())
            path.unlink()

    def test_refuses_symlink(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            target = root / "target"
            target.write_text("{}", encoding="utf-8")
            path = root / "lease.json"
            path.symlink_to(target)
            self.assertFalse(ui_lease_active(path))
            with self.assertRaisesRegex(ValueError, "symlink"):
                create_ui_lease(path)


if __name__ == "__main__":
    unittest.main()
