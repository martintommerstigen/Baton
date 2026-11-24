import tempfile
from pathlib import Path
import subprocess
import unittest
from baton_update_preflight import inspect_checkout, REQUIRED

class UpdatePreflightTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/"repo"
        self.root.mkdir()
        subprocess.run(["git","init","-q",str(self.root)],check=True)
        for name in REQUIRED:
            (self.root/name).write_text("# test\n")
        subprocess.run(["git","-C",str(self.root),"-c","user.name=Test","-c","user.email=test@example.invalid","add","."],check=True)
        subprocess.run(["git","-C",str(self.root),"-c","user.name=Test","-c","user.email=test@example.invalid","commit","-qm","test"],check=True)
    def test_valid_checkout_is_read_only(self):
        result=inspect_checkout(self.root)
        self.assertTrue(result["ok"])
        self.assertFalse(result["update_performed"])
    def test_missing_file_rejected(self):
        (self.root/REQUIRED[0]).unlink()
        self.assertFalse(inspect_checkout(self.root)["ok"])
    def test_symlinked_required_file_rejected(self):
        (self.root/REQUIRED[0]).unlink()
        (self.root/REQUIRED[0]).symlink_to(self.root/REQUIRED[1])
        self.assertFalse(inspect_checkout(self.root)["ok"])
    def test_symlinked_checkout_rejected(self):
        link=Path(self.temp.name)/"linked"
        link.symlink_to(self.root)
        self.assertFalse(inspect_checkout(link)["ok"])
    def test_non_git_dir_rejected(self):
        (self.root/".git").rename(self.root/"_git")
        self.assertFalse(inspect_checkout(self.root)["ok"])

if __name__=="__main__":
    unittest.main()
