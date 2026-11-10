import tempfile
import unittest
from pathlib import Path
from remote_security.pause_guard import pause_active, require_not_paused_now, UIWritesPaused


class PauseGuardTests(unittest.TestCase):
    def test_dangling_symlink_is_pause(self):
        with tempfile.TemporaryDirectory() as root:
            marker = Path(root) / 'PAUSE_UI_WRITES'
            marker.symlink_to(Path(root) / 'missing')
            self.assertFalse(marker.exists())  # Negative control: vulnerable API
            self.assertTrue(pause_active(marker))
            with self.assertRaises(UIWritesPaused):
                require_not_paused_now(marker)

    def test_pause_inserted_after_status_is_caught_by_preclick_check(self):
        with tempfile.TemporaryDirectory() as root:
            marker = Path(root) / 'PAUSE_UI_WRITES'
            self.assertFalse(pause_active(marker))  # Earlier transport observation
            marker.write_text('pause')
            with self.assertRaises(UIWritesPaused):
                require_not_paused_now(marker)

    def test_absence_is_not_a_permission_lease(self):
        with tempfile.TemporaryDirectory() as root:
            marker = Path(root) / 'PAUSE_UI_WRITES'
            self.assertIsNone(require_not_paused_now(marker))
            marker.write_text('pause')
            with self.assertRaises(UIWritesPaused):
                require_not_paused_now(marker)


if __name__ == '__main__':
    unittest.main()
