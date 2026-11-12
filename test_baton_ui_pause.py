"""Greg-local pause gate controls; no UI messages are sent by these tests."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import inspect
import unittest

from baton_ui_pause import ui_writes_paused


class BatonUIPauseTests(unittest.TestCase):
    def test_missing_flag_is_not_paused(self):
        with TemporaryDirectory() as tmp:
            self.assertFalse(ui_writes_paused(Path(tmp) / "PAUSE_UI_WRITES"))

    def test_existing_file_blocks(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "PAUSE_UI_WRITES"
            path.write_text("unresolved existing chat delivery")
            self.assertTrue(ui_writes_paused(path))
            self.assertEqual(path.read_text(), "unresolved existing chat delivery")

    def test_directory_and_dangling_symlink_block(self):
        with TemporaryDirectory() as tmp:
            directory = Path(tmp) / "PAUSE_UI_WRITES"
            directory.mkdir()
            self.assertTrue(ui_writes_paused(directory))
            link = Path(tmp) / "dangling"
            link.symlink_to(Path(tmp) / "missing")
            self.assertTrue(ui_writes_paused(link))

    def test_read_errors_fail_closed(self):
        with patch.object(Path, "lstat", side_effect=PermissionError("denied")):
            self.assertTrue(ui_writes_paused("irrelevant"))
        with patch.object(Path, "lstat", side_effect=OSError("io")):
            self.assertTrue(ui_writes_paused("irrelevant"))
        with patch.object(Path, "lstat", side_effect=FileNotFoundError()):
            self.assertFalse(ui_writes_paused("irrelevant"))

    def test_bridge_rechecks_pause_at_click_boundaries(self):
        from baton_model_bridge import attach_model_bridge
        source = inspect.getsource(attach_model_bridge)
        self.assertIn("from baton_ui_pause import ui_writes_paused",
                      Path(__file__).with_name("baton_model_bridge.py").read_text())
        # A guard in startup alone cannot protect a delayed click.
        self.assertIn("if ui_writes_paused():\n                    finish_relay", source)
        self.assertIn("if ui_writes_paused():\n                    report", source)
        self.assertIn("if ui_writes_paused():\n            results.put", source)
        self.assertIn("if ui_writes_paused():\n            report", source)

    def test_manual_panel_rechecks_pause_and_binds_composer_text(self):
        from baton_conversation_panel import attach_baton_panel
        source = inspect.getsource(attach_baton_panel)
        self.assertIn("def send_message():\n        if ui_writes_paused():", source)
        self.assertIn("def click_once():\n                if ui_writes_paused():", source)
        self.assertIn("send_click_script(wrapped)", source)
        self.assertIn("verified_reply_observation(result)", source)


if __name__ == "__main__":
    unittest.main()
