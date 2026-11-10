import importlib.util
from pathlib import Path
import tempfile
import unittest
import sys

SOURCE = Path(__file__).resolve().parents[1] / "desktop" / "install_baton_launcher.py"
spec = importlib.util.spec_from_file_location("baton_desktop_installer", SOURCE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class LauncherTests(unittest.TestCase):
    def test_entry_is_local_help_only(self):
        with tempfile.TemporaryDirectory() as d:
            client = Path(d) / "client.py"
            client.write_text("print('hi')", encoding="utf-8")
            entry = module.desktop_entry(sys.executable, client)
            self.assertIn("Terminal=true", entry)
            self.assertIn(" --help", entry)
            self.assertNotIn("BATON_TOKEN", entry)
            self.assertNotIn("server.py", entry)
    def test_install_and_refuse_symlink(self):
        with tempfile.TemporaryDirectory() as d:
            client = Path(d) / "client.py"
            client.write_text("", encoding="utf-8")
            dest = Path(d) / "baton.desktop"
            self.assertEqual(module.install(client, dest), dest)
            self.assertIn("[Desktop Entry]", dest.read_text())
            dest.unlink()
            dest.symlink_to(client)
            with self.assertRaises(ValueError):
                module.install(client, dest)
    def test_reject_percent_and_wrong_file(self):
        with tempfile.TemporaryDirectory() as d:
            client = Path(d) / "not_client.py"
            client.write_text("", encoding="utf-8")
            with self.assertRaises(ValueError):
                module.desktop_entry(sys.executable, client)
            client = Path(d) / "client.py"
            client.write_text("", encoding="utf-8")
            bad = Path(d) / "percent%dir"
            bad.mkdir()
            bad_client = bad / "client.py"
            bad_client.write_text("", encoding="utf-8")
            with self.assertRaises(ValueError):
                module.desktop_entry(sys.executable, bad_client)

if __name__ == "__main__":
    unittest.main()
