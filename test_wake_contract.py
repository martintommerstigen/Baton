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
