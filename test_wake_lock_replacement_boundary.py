"""B1/B5 NEG: an advisory pathname lock cannot defend hostile same-UID replacement.

The split-lock counterexample still passes; a post-section identity check now
rejects false success and leaves any post-click delivery uncertain. NOT live UI.
Runs only in a temporary directory and never touches the production lock.
"""
from pathlib import Path
import subprocess
import hashlib
import sys
import tempfile
import unittest

from wake_ui_lock import ui_controller_lock, LockingUIDriver
from wake_adapter import wake_once
from wake_contract import WakeLedger


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
        with self.assertRaisesRegex(PermissionError, 'delivery uncertain'):
            with ui_controller_lock(self.lock):
                original_inode = self.lock.stat().st_ino
                orphan = self.root / 'private' / 'orphaned-original-lock'
                self.lock.rename(orphan)  # hostile same-UID replacement after validation
                self.lock.touch(mode=0o600)
                self.assertNotEqual(original_inode, self.lock.stat().st_ino)
                # NEG remains: both processes hold locks on different inodes.
                self.assertEqual(self.child_result(), 'ACQUIRED')
                self.assertEqual(orphan.stat().st_ino, original_inode)


    def test_transient_replacement_and_restore_can_escape_postcheck(self):
        """NEG: postcheck is not a same-UID mutual-exclusion guarantee."""
        with ui_controller_lock(self.lock):
            original_inode = self.lock.stat().st_ino
            orphan = self.root / 'private' / 'original-temporary'
            self.lock.rename(orphan)
            self.lock.touch(mode=0o600)
            # A second writer can enter while the first holds the old inode.
            self.assertEqual(self.child_result(), 'ACQUIRED')
            self.lock.unlink()
            orphan.rename(self.lock)
            self.assertEqual(self.lock.stat().st_ino, original_inode)
        # No postcheck error: restoration erased pathname evidence.
        # Therefore this check cannot establish exclusive execution.

    def test_parent_directory_replacement_is_detected_on_exit(self):
        with self.assertRaisesRegex(PermissionError, 'delivery uncertain'):
            with ui_controller_lock(self.lock):
                self.lock.parent.rename(self.root / 'orphaned-parent')
                self.lock.parent.mkdir(mode=0o700)
                self.lock.touch(mode=0o600)

    def test_deleted_lock_path_is_detected_on_exit(self):
        with self.assertRaisesRegex(PermissionError, 'delivery uncertain'):
            with ui_controller_lock(self.lock):
                self.lock.unlink()

    def test_post_click_replacement_survives_restart_without_resend(self):
        class SimulatedClick:
            def __init__(self, lock_path):
                self.lock_path = lock_path
                self.clicks = 0

            def submit_once(self, target, message_id, body):
                self.clicks += 1
                self.lock_path.rename(self.lock_path.with_suffix('.orphan'))
                self.lock_path.touch(mode=0o600)

            def observe_reply(self, *args):
                raise AssertionError('post-click lock mismatch must block verification')

        db = self.root / 'wake.sqlite3'
        ledger = WakeLedger(db)
        simulated = SimulatedClick(self.lock)
        driver = LockingUIDriver(simulated, self.lock)
        body = 'harmless preapproved text'
        digest = hashlib.sha256(body.encode('utf-8')).hexdigest()
        args = ('m1', 'A', 'B', digest, body, 'assistant-a')
        with self.assertRaisesRegex(PermissionError, 'delivery uncertain'):
            wake_once(ledger, driver, *args)
        self.assertEqual(ledger.state('m1')[1], 'uncertain')
        self.assertEqual(simulated.clicks, 1)

        # A process restart must not silently click the same message again.
        ledger = WakeLedger(db)
        self.assertEqual(wake_once(ledger, driver, *args), 'uncertain')
        self.assertEqual(simulated.clicks, 1)


if __name__ == '__main__':
    unittest.main()
