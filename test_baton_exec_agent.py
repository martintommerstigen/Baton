import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from baton_exec_agent import execute_command
from baton_github_bus import make_response

class ExecAgentTests(unittest.TestCase):
    def test_exec_disabled_by_default(self):
        with tempfile.TemporaryDirectory() as d:
            rid="f"*32
            p=Path(d)/(rid+".json")
            p.write_text(json.dumps({"id":rid,"operation":"exec",
                "created_at":datetime.now(timezone.utc).isoformat(),
                "argv":["python3","-c","print(123)"],"cwd":d,"timeout":5}))
            self.assertEqual(make_response(p,Path(d),datetime.now(timezone.utc))["status"],"rejected")
            with patch("baton_exec_agent.os.geteuid",return_value=1000):
                result=make_response(p,Path(d),datetime.now(timezone.utc),enable_exec=True)
            self.assertEqual(result["status"],"executed")
            self.assertEqual(result["result"]["output"].strip(),"123")
    def test_bad_argv_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                execute_command(["echo","x\x00y"],d)
    def test_root_denied(self):
        with tempfile.TemporaryDirectory() as d:
            with patch("baton_exec_agent.os.geteuid",return_value=0):
                with self.assertRaises(PermissionError):
                    execute_command(["true"],d)
    def test_timeout_bounded(self):
        with tempfile.TemporaryDirectory() as d:
            with patch("baton_exec_agent.os.geteuid",return_value=1000):
                result=execute_command(["python3","-c","import time; time.sleep(3)"],d,timeout=1)
            self.assertTrue(result["timeout"])
if __name__=="__main__":
    unittest.main()
