"""Offline tests for Greg preflight; never inspect real home state."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parent / "desktop" / "preflight_greg.py"
spec = importlib.util.spec_from_file_location("preflight_greg", SOURCE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class GregPreflightTests(unittest.TestCase):
    def test_no_remote_access_claim(self):
        result = module.check()
        self.assertIs(result["ready_for_chatgpt_terminal"], False)
        self.assertIn("ui_writes_paused_or_unverifiable", result)

    def test_symlinked_pause_ancestor_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            actual = root / "actual"
            actual.mkdir()
            alias = root / "alias"
            alias.symlink_to(actual, target_is_directory=True)
            with patch.object(module, "PAUSE_PATH", alias / "PAUSE_UI_WRITES", create=True):
                self.assertTrue(module.check()["ui_writes_paused_or_unverifiable"])

if __name__ == "__main__":
    unittest.main()
