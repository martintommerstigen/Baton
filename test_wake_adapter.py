import tempfile
import unittest
from wake_contract import WakeLedger
from wake_adapter import wake_once, reconcile, Observation

class Driver:
    def __init__(self, reply=None):
        self.calls=[]
        self.reply=reply
    def submit_once(self, conversation_id, message_id, body):
        self.calls.append((conversation_id,message_id,body))
    def observe_reply(self, conversation_id, message_id, digest):
        return self.reply

class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.ledger=WakeLedger(self.tmp.name+"/db")
    def tearDown(self): self.tmp.cleanup()
    def wake(self,driver):
        return wake_once(self.ledger,driver,"msg","A","B","digest","hello")
    def test_verified(self):
        d=Driver(Observation("B","turn"))
        self.assertEqual(self.wake(d),"verified")
        self.assertEqual(len(d.calls),1)
    def test_no_retry_after_unknown(self):
        d=Driver()
        self.assertEqual(self.wake(d),"uncertain")
        self.assertEqual(self.wake(d),"uncertain")
        self.assertEqual(len(d.calls),1)
    def test_read_only_reconcile(self):
        d=Driver()
        self.wake(d)
        d.reply=Observation("B","turn")
        self.assertEqual(reconcile(self.ledger,d,"msg"),"verified")
        self.assertEqual(len(d.calls),1)
    def test_wrong_chat_not_verified(self):
        d=Driver(Observation("C","turn"))
        with self.assertRaises(ValueError): self.wake(d)
        self.assertEqual(self.ledger.state("msg")[1],"uncertain")
    def test_crash_does_not_resubmit(self):
        self.ledger.request("msg","A","B","digest")
        self.ledger.begin_submission("msg")
        d=Driver(Observation("B","turn"))
        self.assertEqual(self.wake(d),"submitting")
        self.assertEqual(d.calls,[])
        self.assertEqual(reconcile(self.ledger,d,"msg"),"verified")

if __name__=="__main__": unittest.main()
