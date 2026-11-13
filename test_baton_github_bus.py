"""Offline checks for private GitHub Baton bus. No network or real repo access."""
import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
import unittest
from baton_github_bus import make_response, process_pending_requests

class PrivateBusTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.workspace=Path(self.temp.name)
        self.now=datetime.now(timezone.utc)
        self.req_id="1234567890abcdef1234567890abcdef"
        self.request=self.workspace/(self.req_id+".json")
    def make(self,operation="identity",time=None,extra=None):
        payload={"id":self.req_id,"operation":operation,
                 "created_at":(time or self.now).isoformat()}
        if extra:
            payload.update(extra)
        self.request.write_text(json.dumps(payload))
        return make_response(self.request,self.workspace,self.now)
    def test_identity(self):
        response=self.make()
        self.assertEqual(response["status"],"executed")
        self.assertTrue(response["result"]["ok"])
    def test_arbitrary_shell_denied(self):
        self.assertEqual(self.make("sh -c id")["status"],"rejected")
    def test_expired_denied(self):
        self.assertEqual(self.make(time=self.now-timedelta(hours=7))["status"],"rejected")
    def test_future_request_denied(self):
        self.assertEqual(self.make(time=self.now+timedelta(minutes=2))["status"],"rejected")
    def test_extra_keys_denied(self):
        self.assertEqual(self.make(extra={"workspace":"/tmp"})["status"],"rejected")
    def test_mismatched_id_denied(self):
        self.request.write_text(json.dumps({"id":"0"*32,"operation":"identity",
                         "created_at":self.now.isoformat()}))
        self.assertEqual(make_response(self.request,self.workspace,self.now)["status"],"rejected")
    def test_invalid_json_denied(self):
        self.request.write_text("{broken")
        self.assertEqual(make_response(self.request,self.workspace,self.now)["status"],"rejected")
    def test_oversized_denied(self):
        self.request.write_text("x"*2000)
        self.assertEqual(make_response(self.request,self.workspace,self.now)["status"],"rejected")
    def test_symlinked_request_denied(self):
        target=self.workspace/"target"
        target.write_text("{}")
        self.request.symlink_to(target)
        self.assertEqual(make_response(self.request,self.workspace,self.now)["status"],"rejected")
    def test_acknowledged_history_does_not_starve_new_requests(self):
        req_dir=self.workspace/"requests"
        res_dir=self.workspace/"responses"
        req_dir.mkdir()
        res_dir.mkdir()
        for i in range(35):
            request_id=f"{i:032x}"
            (req_dir/(request_id+".json")).write_text(json.dumps({
                "id":request_id,"operation":"identity","created_at":self.now.isoformat()}))
            if i < 34:
                (res_dir/(request_id+".json")).write_text("{}")
        self.assertEqual(process_pending_requests(req_dir,res_dir,self.workspace,self.now),1)
        self.assertTrue((res_dir/(f"{34:032x}.json")).is_file())
    def test_request_batch_limit(self):
        req_dir=self.workspace/"requests"
        res_dir=self.workspace/"responses"
        req_dir.mkdir()
        res_dir.mkdir()
        for i in range(4):
            request_id=f"{i:032x}"
            (req_dir/(request_id+".json")).write_text(json.dumps({
                "id":request_id,"operation":"identity","created_at":self.now.isoformat()}))
        self.assertEqual(process_pending_requests(req_dir,res_dir,self.workspace,self.now,limit=2),2)
        self.assertEqual(process_pending_requests(req_dir,res_dir,self.workspace,self.now,limit=2),2)
        self.assertEqual(process_pending_requests(req_dir,res_dir,self.workspace,self.now,limit=2),0)
if __name__=="__main__":
    unittest.main()
