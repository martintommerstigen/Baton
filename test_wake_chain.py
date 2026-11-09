import tempfile
import unittest
from wake_contract import WakeLedger
from wake_adapter import Observation
from wake_chain import ChainPlan, next_target_from_reply, run_chain

class Driver:
    def __init__(self, chat):
        self.chat=chat
        self.sends=[]
    def submit_once(self, chat, mid, body):
        self.sends.append((chat,mid,body))
    def observe_reply(self, chat, mid):
        return Observation(self.chat,mid+'-assistant')

class ChainTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.ledger=WakeLedger(self.tmp.name+'/db')
        self.plan=ChainPlan('A','B','C','one','two','ask B','ask C','d1','d2')
        self.b=Driver('B')
        self.c=Driver('C')
    def tearDown(self): self.tmp.cleanup()
    def test_explicit_request(self):
        self.assertEqual(next_target_from_reply('Hello\nBATON_NEXT C','C'),'C')
        self.assertIsNone(next_target_from_reply('BATON_NEXT D','C'))
        self.assertIsNone(next_target_from_reply('BATON_NEXT C\nBATON_NEXT C','C'))
    def test_verified_chain(self):
        result=run_chain(self.ledger,self.b,self.c,self.plan,
                         lambda chat,turn:'BATON_NEXT C')
        self.assertEqual(result,{'a_to_b':'verified','b_to_c':'verified'})
        self.assertEqual(len(self.b.sends),1)
        self.assertEqual(len(self.c.sends),1)
    def test_no_second_send_without_request(self):
        result=run_chain(self.ledger,self.b,self.c,self.plan,
                         lambda chat,turn:'I have not authorized the next wake')
        self.assertEqual(result['b_to_c'],'not_authorized')
        self.assertEqual(self.c.sends,[])
    def test_no_replay(self):
        reader=lambda chat,turn:'BATON_NEXT C'
        run_chain(self.ledger,self.b,self.c,self.plan,reader)
        run_chain(self.ledger,self.b,self.c,self.plan,reader)
        self.assertEqual(len(self.b.sends),1)
        self.assertEqual(len(self.c.sends),1)
    def test_distinct_conversations(self):
        p=ChainPlan('A','A','C','one','two','x','y','d1','d2')
        with self.assertRaises(ValueError):
            run_chain(self.ledger,self.b,self.c,p,lambda a,b:'BATON_NEXT C')

if __name__=='__main__': unittest.main()
