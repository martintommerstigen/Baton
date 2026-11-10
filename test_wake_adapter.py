import tempfile
import hashlib
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
        return wake_once(self.ledger,driver,"msg","A","B",
                         hashlib.sha256(b"hello").hexdigest(),"hello")
    def test_mismatched_body_rejected_before_ledger_or_send(self):
        d=Driver(Observation("B","turn"))
        approved=hashlib.sha256(b"approved body").hexdigest()
        with self.assertRaisesRegex(ValueError,"approved SHA-256"):
            wake_once(self.ledger,d,"msg","A","B",approved,"tampered body")
        self.assertIsNone(self.ledger.state("msg"))
        self.assertEqual(d.calls,[])

    def test_mismatched_body_cannot_replay_verified_receipt(self):
        d=Driver(Observation("B","turn"))
        self.assertEqual(self.wake(d),"verified")
        approved=hashlib.sha256(b"hello").hexdigest()
        with self.assertRaisesRegex(ValueError,"approved SHA-256"):
            wake_once(self.ledger,d,"msg","A","B",approved,"other body")
        self.assertEqual(len(d.calls),1)
        self.assertEqual(self.ledger.state("msg")[1],"verified")

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
    def test_unresolved_same_target_never_calls_ui_driver(self):
        first=Driver()
        self.assertEqual(self.wake(first),'uncertain')
        second=Driver(Observation("B","other-turn"))
        with self.assertRaisesRegex(RuntimeError,'unresolved wake'):
            wake_once(self.ledger,second,'other','C','B','other-digest','other body')
        self.assertEqual(second.calls,[])
        self.assertEqual(self.ledger.state('other')[1],'requested')
        first.reply=Observation("B","first-turn")
        self.assertEqual(reconcile(self.ledger,first,'msg'),'verified')
        self.assertEqual(wake_once(self.ledger,second,'other','C','B','other-digest','other body'),
                         'verified')
        self.assertEqual(len(second.calls),1)

    def test_wrong_chat_not_verified(self):
        d=Driver(Observation("C","turn"))
        with self.assertRaises(ValueError): self.wake(d)
        self.assertEqual(self.ledger.state("msg")[1],"uncertain")
    def test_crash_does_not_resubmit(self):
        self.ledger.request("msg","A","B",hashlib.sha256(b"hello").hexdigest())
        self.ledger.begin_submission("msg")
        d=Driver(Observation("B","turn"))
        self.assertEqual(self.wake(d),"submitting")
        self.assertEqual(d.calls,[])
        self.assertEqual(reconcile(self.ledger,d,"msg"),"verified")

if __name__=="__main__": unittest.main()
