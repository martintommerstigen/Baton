"""B1/B5 NEG: an advisory pathname lock cannot defend hostile same-UID replacement.

This is an intentionally passing counterexample, NOT a mitigation or a live UI test.
Runs only in a temporary directory and never touches the production lock.
"""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from wake_ui_lock import ui_controller_lock


CHILD = """import sys
from wake_ui_lock import ui_controller_lock
try:
    with ui_controller_lock(sys.argv[1]):
        print('ACQUIRED', flush=True)
except RuntimeError:
    print('BLOCKED', flush=True)
"""


class PathnameReplacementBoundary(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.lock = self.root / 'private' / 'ui.lock'
        self.lock.parent.mkdir(mode=0o700)

    def child_result(self):
        p = subprocess.run([sys.executable, '-c', CHILD, str(self.lock)],
                           cwd=str(Path(__file__).resolve().parent),
                           capture_output=True, text=True, timeout=5, check=True)
        return p.stdout.strip()

    def test_same_inode_excludes_cooperating_second_process(self):
        with ui_controller_lock(self.lock):
            self.assertEqual(self.child_result(), 'BLOCKED')
        self.assertEqual(self.child_result(), 'ACQUIRED')

    def test_post_validation_path_replacement_splits_lock_domain(self):
        with ui_controller_lock(self.lock):
            original_inode = self.lock.stat().st_ino
            orphan = self.root / 'private' / 'orphaned-original-lock'
            self.lock.rename(orphan)  # hostile same-UID replacement after validation
            self.lock.touch(mode=0o600)
            self.assertNotEqual(original_inode, self.lock.stat().st_ino)
            # Both processes hold EX locks on *different* inodes concurrently.
            self.assertEqual(self.child_result(), 'ACQUIRED')
            self.assertEqual(orphan.stat().st_ino, original_inode)


if __name__ == '__main__':
    unittest.main()
