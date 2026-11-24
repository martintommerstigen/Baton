import tempfile
import unittest
from pathlib import Path
from remote_security.chatgpt_greg_dispatch import AuthenticatedGregDispatcher

class DispatcherTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.calls=[]
        def transport(sock,argv):
            self.calls.append((sock,argv))
            return {"state":"completed","returncode":0,"stdout":"ok","stderr":"","truncated":False}
        self.dispatch=AuthenticatedGregDispatcher(
            str(Path(self.temp.name)/"jobs.sqlite"),b"k"*32,"/tmp/unused.sock",
            {"chat-1"},{"/usr/bin/id"},clock=lambda:1000,transport=transport)
        self.req={"job_id":"unique-job-001","conversation_id":"chat-1",
                  "issued_at":1000,"argv":["/usr/bin/id"]}
    def test_signed_once_and_replay(self):
        sig=self.dispatch.sign(self.req)
        self.assertEqual(self.dispatch.dispatch(self.req,sig)["state"],"completed")
        self.assertEqual(self.dispatch.dispatch(self.req,sig)["state"],"completed")
        self.assertEqual(len(self.calls),1)
    def test_invalid_signature(self):
        with self.assertRaises(PermissionError):
            self.dispatch.dispatch(self.req,"bad")
        self.assertEqual(self.calls,[])
    def test_unapproved_executable(self):
        self.req["argv"]=["/bin/sh","-c","echo unsafe"]
        with self.assertRaises(PermissionError):
            self.dispatch.dispatch(self.req,self.dispatch.sign(self.req))
    def test_collision(self):
        self.dispatch.dispatch(self.req,self.dispatch.sign(self.req))
        self.req["argv"]=["/usr/bin/id","-u"]
        with self.assertRaises(ValueError):
            self.dispatch.dispatch(self.req,self.dispatch.sign(self.req))
    def test_uncertain_not_retried(self):
        def failed(*args): raise ConnectionError("unknown")
        self.dispatch.transport=failed
        with self.assertRaises(ConnectionError):
            self.dispatch.dispatch(self.req,self.dispatch.sign(self.req))
        self.dispatch.transport=lambda *a: self.fail("replayed")
        self.assertEqual(self.dispatch.dispatch(self.req,self.dispatch.sign(self.req))["state"],
                         "started_uncertain")
if __name__=="__main__": unittest.main()
