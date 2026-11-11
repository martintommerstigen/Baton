import tempfile
import hashlib
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
    def observe_reply(self, chat, mid, digest):
        return Observation(self.chat,mid+'-assistant')

class ChainTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.ledger=WakeLedger(self.tmp.name+'/db')
        self.plan=ChainPlan('A','B','C','one','two','ask B','ask C',
                            hashlib.sha256(b'ask B').hexdigest(),
                            hashlib.sha256(b'ask C').hexdigest())
        self.b=Driver('B')
        self.c=Driver('C')
        self.next_command=f'BATON_NEXT C sha256:{self.plan.second_digest}'
    def tearDown(self): self.tmp.cleanup()
    def test_explicit_request(self):
        self.assertEqual(next_target_from_reply('BATON_NEXT C','C'),'C')
        self.assertIsNone(next_target_from_reply('Hello\nBATON_NEXT C','C'))
        self.assertIsNone(next_target_from_reply('```\nBATON_NEXT C\n```','C'))
        self.assertIsNone(next_target_from_reply('BATON_NEXT D','C'))
        self.assertIsNone(next_target_from_reply('BATON_NEXT C\nBATON_NEXT C','C'))
    def test_exact_digest_required_for_legacy_runner(self):
        # The older PR #4 runner must not bypass H17's payload authority:
        # B authorizes C AND the exact approved UTF-8 body, not C alone.
        for reply in (
            'BATON_NEXT C',
            'BATON_NEXT C sha256:' + '0' * 64,
            self.next_command + '\\n',
            ' ' + self.next_command,
            self.next_command + ' ',
            'Example: ' + self.next_command,
            'BATON_NEXT C sha256:' + self.plan.second_digest.upper(),
        ):
            with self.subTest(reply=reply):
                self.assertIsNone(next_target_from_reply(reply,'C',self.plan.second_digest))

    def test_legacy_runner_denies_digestless_b_without_c_send(self):
        result=run_chain(self.ledger,self.b,self.c,self.plan,
                         lambda chat,turn:'BATON_NEXT C')
        self.assertEqual(result['a_to_b'],'verified')
        self.assertEqual(result['b_to_c'],'not_authorized')
        self.assertEqual(self.c.sends,[])
        self.assertIsNone(self.ledger.provenance('two'))

    def test_wrong_digest_denies_even_if_b_requests_same_c(self):
        result=run_chain(self.ledger,self.b,self.c,self.plan,
                         lambda chat,turn:'BATON_NEXT C sha256:'+'0'*64)
        self.assertEqual(result['b_to_c'],'not_authorized')
        self.assertEqual(self.c.sends,[])

    def test_both_hops_have_source_turn_provenance(self):
        from dataclasses import replace
        plan=replace(self.plan,origin_turn_id='a-turn-123')
        result=run_chain(self.ledger,self.b,self.c,plan,
                         lambda chat,turn:self.next_command)
        self.assertEqual(result['b_to_c'],'verified')
        self.assertEqual(self.ledger.provenance('one')[2],'a-turn-123')
        self.assertEqual(self.ledger.provenance('two')[2],'one-assistant')
    def test_verified_chain(self):
        result=run_chain(self.ledger,self.b,self.c,self.plan,
                         lambda chat,turn:self.next_command)
        self.assertEqual(result,{'a_to_b':'verified','b_to_c':'verified'})
        self.assertEqual(len(self.b.sends),1)
        self.assertEqual(len(self.c.sends),1)
    def test_no_second_send_without_request(self):
        result=run_chain(self.ledger,self.b,self.c,self.plan,
                         lambda chat,turn:'I have not authorized the next wake')
        self.assertEqual(result['b_to_c'],'not_authorized')
        self.assertEqual(self.c.sends,[])
    def test_no_replay(self):
        reader=lambda chat,turn:self.next_command
        run_chain(self.ledger,self.b,self.c,self.plan,reader)
        run_chain(self.ledger,self.b,self.c,self.plan,reader)
        self.assertEqual(len(self.b.sends),1)
        self.assertEqual(len(self.c.sends),1)
    def test_reconcile_crashed_first_hop_without_resend(self):
        self.ledger.request('one','A','B',self.plan.first_digest)
        self.ledger.begin_submission('one')
        result=run_chain(self.ledger,self.b,self.c,self.plan,
                         lambda chat,turn:self.next_command)
        self.assertEqual(result['a_to_b'],'verified')
        self.assertEqual(self.b.sends,[])
        self.assertEqual(len(self.c.sends),1)
    def test_reconcile_crashed_second_hop_without_resend(self):
        self.ledger.request('two','B','C',self.plan.second_digest,'one-assistant')
        self.ledger.begin_submission('two')
        result=run_chain(self.ledger,self.b,self.c,self.plan,
                         lambda chat,turn:self.next_command)
        self.assertEqual(result['b_to_c'],'verified')
        self.assertEqual(self.c.sends,[])
    def test_distinct_conversations(self):
        p=ChainPlan('A','A','C','one','two','x','y','d1','d2')
        with self.assertRaises(ValueError):
            run_chain(self.ledger,self.b,self.c,p,lambda a,b:self.next_command)

if __name__=='__main__': unittest.main()
