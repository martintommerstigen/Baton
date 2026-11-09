import tempfile
import unittest
from wake_contract import WakeLedger

class WakeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.path=self.tmp.name+"/ledger.db"
        self.w=WakeLedger(self.path)
    def tearDown(self): self.tmp.cleanup()
    def req(self): return self.w.request("id1","chat-A","chat-B","sha256:test")
    def test_replay_conflict(self):
        self.assertEqual(self.req(),"requested")
        self.assertEqual(self.req(),"requested")
        with self.assertRaises(ValueError):
            self.w.request("id1","chat-A","chat-C","sha256:test")
    def test_no_queue_as_wake(self):
        self.req()
        with self.assertRaises(ValueError): self.w.verify("id1","chat-B","turn1")
    def test_wrong_chat(self):
        self.req();self.w.begin_submission("id1")
        with self.assertRaises(ValueError): self.w.verify("id1","chat-C","turn1")
    def test_uncertain_verified(self):
        self.req()
        self.assertTrue(self.w.begin_submission("id1"))
        self.assertFalse(self.w.begin_submission("id1"))
        self.assertTrue(self.w.mark_uncertain("id1"))
        self.assertTrue(self.w.verify("id1","chat-B","turn1"))
        self.assertFalse(self.w.verify("id1","chat-B","turn1"))
    def test_restart(self):
        self.req();self.w.begin_submission("id1")
        self.assertEqual(WakeLedger(self.path).state("id1")[1],"submitting")
        self.assertFalse(WakeLedger(self.path).begin_submission("id1"))
    def test_missing_turn(self):
        self.req();self.w.begin_submission("id1")
        with self.assertRaises(ValueError): self.w.verify("id1","chat-B","")

if __name__=="__main__": unittest.main()
