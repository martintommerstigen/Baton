"""Offline tests for the Greg executor; no live host access claimed."""
import sys
import tempfile
import unittest
from remote_security.greg_executor import execute

class GregExecutorTests(unittest.TestCase):
    def test_executes_without_shell(self):
        with tempfile.TemporaryDirectory() as d:
            r=execute({"argv":[sys.executable,"-c","print('ready')"]},d)
            self.assertEqual(r["state"],"completed")
            self.assertEqual(r["stdout"].strip(),"ready")
    def test_writes_as_host_user(self):
        with tempfile.TemporaryDirectory() as d:
            r=execute({"argv":[sys.executable,"-c","open('probe.txt','w').write('baton')"]},d)
            self.assertEqual(r["returncode"],0)
            with open(d+"/probe.txt") as f:
                self.assertEqual(f.read(),"baton")
    def test_rejects_injection_schema(self):
        with tempfile.TemporaryDirectory() as d:
            for req in ({"argv":"echo hello"},{"argv":[]},{"argv":["echo","a\\x00b"]},{"argv":["echo"],"shell":True}):
                with self.assertRaises(ValueError):
                    execute(req,d)
    def test_failed_command_reports_exit(self):
        with tempfile.TemporaryDirectory() as d:
            r=execute({"argv":[sys.executable,"-c","raise SystemExit(7)"]},d)
            self.assertEqual(r["returncode"],7)
if __name__=="__main__": unittest.main()
