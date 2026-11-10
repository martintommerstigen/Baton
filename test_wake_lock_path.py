"""B1/B5 negative tests for unsafe shared host-lock path aliases."""
from pathlib import Path
import tempfile
import unittest
from wake_ui_lock import ui_controller_lock


class LockPathTests(unittest.TestCase):
    def test_symlinked_parent_directory_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            real = root / 'real'
            real.mkdir(mode=0o700)
            alias = root / 'alias'
            alias.symlink_to(real, target_is_directory=True)
            with self.assertRaises(PermissionError):
                with ui_controller_lock(alias / 'lock'):
                    self.fail('must not enter lock via symlink directory')

    def test_hardlinked_lock_file_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            lock = root / 'lock'
            lock.write_text('')
            lock.chmod(0o600)
            (root / 'alias').hardlink_to(lock)
            with self.assertRaises(PermissionError):
                with ui_controller_lock(lock):
                    self.fail('must not enter lock with hardlinked inode')

    def test_relative_or_traversed_lock_path_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for lock in (Path('relative.lock'), root / '..' / 'lock'):
                with self.subTest(path=str(lock)), self.assertRaises(PermissionError):
                    with ui_controller_lock(lock):
                        self.fail('must reject unsafe lock path')

    def test_valid_lock_still_acquires(self):
        with tempfile.TemporaryDirectory() as d:
            lock = Path(d) / 'private' / 'lock'
            with ui_controller_lock(lock):
                self.assertTrue(lock.is_file())


if __name__ == '__main__':
    unittest.main()
