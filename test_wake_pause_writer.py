"""Offline negative tests for the cooperating pause-writer contract."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from wake_pause_writer import activate_pause
from wake_ui_lock import ui_controller_lock
from chatgpt_ui_driver import pause_active, ChatGPTUIDriver
from test_chatgpt_ui_submission import Page, CID
from wake_adapter import PreSubmissionRejected


class CooperativePauseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.parent = self.root / 'transport'
        self.parent.mkdir(mode=0o700)
        self.marker = self.parent / 'PAUSE_UI_WRITES'
        self.lock = self.root / 'locks' / 'chatgpt-ui.lock'

    def tearDown(self):
        self.temp.cleanup()

    def test_create_private_marker_and_preserve_it_on_repeat(self):
        self.assertTrue(activate_pause(self.marker, self.lock))
        inode = self.marker.stat().st_ino
        self.assertTrue(pause_active(self.marker))
        self.assertEqual(self.marker.stat().st_mode & 0o777, 0o600)
        self.assertFalse(activate_pause(self.marker, self.lock))
        self.assertEqual(self.marker.stat().st_ino, inode)

    def test_existing_symlink_is_not_followed_or_replaced(self):
        victim = self.root / 'victim'
        victim.write_text('untouched')
        self.marker.symlink_to(victim)
        self.assertFalse(activate_pause(self.marker, self.lock))
        self.assertEqual(victim.read_text(), 'untouched')
        self.assertTrue(self.marker.is_symlink())

    def test_symlinked_parent_is_rejected(self):
        real = self.root / 'real'
        real.mkdir()
        self.parent.rmdir()
        self.parent.symlink_to(real, target_is_directory=True)
        with self.assertRaises(OSError):
            activate_pause(self.marker, self.lock)
        self.assertFalse((real / self.marker.name).exists())

    def test_missing_parent_is_rejected(self):
        with self.assertRaises(OSError):
            activate_pause(self.root / 'missing' / 'PAUSE_UI_WRITES', self.lock)

    def test_relative_and_traversal_paths_are_rejected(self):
        for value in ('relative/PAUSE_UI_WRITES', str(self.root / '..' / 'elsewhere' / 'PAUSE_UI_WRITES')):
            with self.subTest(value=value), self.assertRaises(ValueError):
                activate_pause(value, self.lock)

    def test_sender_holds_lock_writer_fails_and_cannot_claim_pause(self):
        with ui_controller_lock(self.lock):
            page = Page()
            with patch('chatgpt_ui_driver.PAUSE_FILE', self.marker):
                ChatGPTUIDriver(page, frozenset({CID})).submit_once(CID, 'before-pause', 'harmless')
            self.assertEqual(page.send.clicks, 1)
            with self.assertRaises(RuntimeError):
                activate_pause(self.marker, self.lock)
            self.assertFalse(self.marker.exists())
        self.assertTrue(activate_pause(self.marker, self.lock))
        page2 = Page()
        with patch('chatgpt_ui_driver.PAUSE_FILE', self.marker):
            with self.assertRaises(PreSubmissionRejected):
                ChatGPTUIDriver(page2, frozenset({CID})).submit_once(CID, 'after-pause', 'harmless')
        self.assertEqual(page2.send.clicks, 0)

    def test_pause_first_blocks_sender_without_click(self):
        self.assertTrue(activate_pause(self.marker, self.lock))
        page = Page()
        with ui_controller_lock(self.lock), patch('chatgpt_ui_driver.PAUSE_FILE', self.marker):
            with self.assertRaises(PreSubmissionRejected):
                ChatGPTUIDriver(page, frozenset({CID})).submit_once(CID, 'blocked', 'harmless')
        self.assertEqual(page.send.clicks, 0)

    def test_cross_process_contention_does_not_create_marker(self):
        script = ("import sys, time\nfrom wake_ui_lock import ui_controller_lock\n"
                  "with ui_controller_lock(sys.argv[1]):\n"
                  " print('LOCKED', flush=True)\n time.sleep(1.2)\n")
        child = subprocess.Popen([sys.executable, '-c', script, str(self.lock)],
                                 cwd=str(Path(__file__).parent), stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, text=True)
        try:
            self.assertEqual(child.stdout.readline().strip(), 'LOCKED')
            with self.assertRaises(RuntimeError):
                activate_pause(self.marker, self.lock)
            self.assertFalse(self.marker.exists())
        finally:
            out, err = child.communicate(timeout=5)
        self.assertEqual(child.returncode, 0, err)
        self.assertTrue(activate_pause(self.marker, self.lock))


if __name__ == '__main__':
    unittest.main()
