import tempfile
import sqlite3
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from wake_contract import WakeLedger

class WakeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.path=self.tmp.name+"/ledger.db"
        self.w=WakeLedger(self.path)
    def tearDown(self): self.tmp.cleanup()
    def req(self): return self.w.request("id1","chat-A","chat-B","sha256:test")
    def test_source_turn_persisted_and_conflict(self):
        self.assertEqual(self.w.request('origin','A','B','digest','a-turn-1'),'requested')
        self.assertEqual(self.w.provenance('origin')[2],'a-turn-1')
        self.assertEqual(self.w.request('origin','A','B','digest','a-turn-1'),'requested')
        with self.assertRaises(ValueError):
            self.w.request('origin','A','B','digest','a-turn-2')
        with self.assertRaises(ValueError):
            self.w.request('origin','A','B','digest')
    def test_source_turn_cannot_authorize_two_distinct_wakes(self):
        self.w.request('one','A','B','digest-1','a-turn-1')
        with self.assertRaisesRegex(ValueError,'source assistant turn already used'):
            self.w.request('two','A','C','digest-2','a-turn-1')
        self.assertIsNone(self.w.state('two'))
        # Another assistant turn from A remains independently eligible.
        self.assertEqual(self.w.request('two','A','C','digest-2','a-turn-2'),'requested')
        # B may separately authorize the next hop using its own turn.
        self.assertEqual(self.w.request('three','B','C','digest-3','b-turn-1'),'requested')

    def test_observed_turn_cannot_verify_two_distinct_wakes(self):
        for mid in ('one','two'):
            self.w.request(mid,'A','B','digest-'+mid)
            self.w.begin_submission(mid)
        self.assertTrue(self.w.verify('one','B','same-assistant-turn'))
        with self.assertRaisesRegex(ValueError,'assistant turn already verifies'):
            self.w.verify('two','B','same-assistant-turn')
        self.assertEqual(self.w.state('two')[1],'submitting')
        self.assertIsNone(self.w.state('two')[2])
        # A distinct real assistant turn can verify the second message.
        self.assertTrue(self.w.verify('two','B','different-assistant-turn'))
        self.assertFalse(self.w.verify('one','B','same-assistant-turn'))

    def test_concurrent_turn_claims_are_serialized(self):
        for mid in ('one','two'):
            self.w.request(mid,'A','B','digest-'+mid)
            self.w.begin_submission(mid)
        def claim(mid):
            try:
                return self.w.verify(mid,'B','same-turn')
            except ValueError:
                return False
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(claim,('one','two')))
        self.assertCountEqual(results,[True,False])
        self.assertEqual(sum(self.w.state(mid)[1]=='verified'
                             for mid in ('one','two')),1)

    def test_same_target_inflight_blocks_new_submission(self):
        self.w.request('first','A','B','digest-1','a-turn-1')
        self.w.request('second','C','B','digest-2','c-turn-1')
        self.assertTrue(self.w.begin_submission('first'))
        with self.assertRaisesRegex(RuntimeError,'unresolved wake'):
            self.w.begin_submission('second')
        self.assertEqual(self.w.state('second')[1],'requested')
        self.assertTrue(self.w.mark_uncertain('first'))
        with self.assertRaisesRegex(RuntimeError,'unresolved wake'):
            self.w.begin_submission('second')
        self.assertTrue(self.w.verify('first','B','b-turn-1'))
        self.assertTrue(self.w.begin_submission('second'))

    def test_distinct_targets_can_submit_concurrently(self):
        self.w.request('first','A','B','d1')
        self.w.request('second','A','C','d2')
        self.assertTrue(self.w.begin_submission('first'))
        self.assertTrue(self.w.begin_submission('second'))

    def test_concurrent_same_target_claims_are_serialized(self):
        self.w.request('first','A','B','d1')
        self.w.request('second','C','B','d2')
        def start(mid):
            try:
                return self.w.begin_submission(mid)
            except RuntimeError:
                return False
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(start,('first','second')))
        self.assertCountEqual(results,[True,False])
        self.assertEqual(sum(self.w.state(mid)[1]=='submitting'
                             for mid in ('first','second')),1)
        self.assertEqual(sum(self.w.state(mid)[1]=='requested'
                             for mid in ('first','second')),1)

    def test_migrate_legacy_ledger(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=tmp+'/old.sqlite'
            with closing(sqlite3.connect(path)) as db, db:
                db.execute('CREATE TABLE wakes (id TEXT PRIMARY KEY, source TEXT NOT NULL, target TEXT NOT NULL, digest TEXT NOT NULL, state TEXT NOT NULL, observed_turn TEXT, updated INTEGER NOT NULL)')
                db.execute("INSERT INTO wakes VALUES ('old','A','B','d','requested',NULL,1)")
            migrated=WakeLedger(path)
            self.assertIsNone(migrated.provenance('old')[2])
            self.assertEqual(migrated.request('new','A','C','d','a-turn'),'requested')
            self.assertEqual(migrated.provenance('new')[2],'a-turn')
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
    def test_competing_verifications(self):
        self.req();self.w.begin_submission('id1')
        def attempt(turn):
            try: return self.w.verify('id1','chat-B',turn)
            except ValueError: return 'conflict'
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(attempt,('turn-A','turn-B')))
        self.assertCountEqual(results,[True,'conflict'])
        self.assertIn(self.w.state('id1')[2],('turn-A','turn-B'))
    def test_missing_turn(self):
        self.req();self.w.begin_submission("id1")
        with self.assertRaises(ValueError): self.w.verify("id1","chat-B","")

if __name__=="__main__": unittest.main()
