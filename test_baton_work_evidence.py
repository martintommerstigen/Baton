"""Isolated negative tests of what historical Baton evidence cannot prove."""
import importlib.util
from pathlib import Path
import sqlite3
import tempfile
import unittest

from baton_work_evidence import snapshot

A = "6aef3ac4-86bc-83ed-a4df-89e947bc5a34"
B = "6aef828e-0150-83eb-bbac-061f79a8fd4a"


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.addCleanup(self.t.cleanup)
        root = Path(self.t.name)
        self.topic_db = root / "forum.sqlite3"
        self.wake_db = root / "wakes.sqlite3"
        with sqlite3.connect(self.topic_db) as c:
            c.executescript("""
                CREATE TABLE topics(topic_id TEXT PRIMARY KEY,title TEXT,state TEXT);
                CREATE TABLE discussion_posts(
                  post_id TEXT PRIMARY KEY,topic_id TEXT,claimed_author TEXT,reply_post TEXT
                );
                CREATE TABLE discussion_revisions(
                  post_id TEXT,revision INTEGER,author_run TEXT,kind TEXT,
                  created INTEGER,transport_actor TEXT,verification_state TEXT
                );
                INSERT INTO topics VALUES('continuity-rhythm','Continuity','open');
                INSERT INTO topics VALUES('unrelated-topic','Other','open');
            """)

    def add(self,pid,topic,author,created,revision=1):
        with sqlite3.connect(self.topic_db) as c:
            c.execute("INSERT OR IGNORE INTO discussion_posts VALUES(?,?,?,NULL)",
                      (pid,topic,author))
            c.execute("INSERT INTO discussion_revisions VALUES(?,?,?,?,?,?,?)",
                      (pid,revision,"local-script","note",created,
                       "local-os:1000","claimed_local_writer"))

    def test_other_topic_cannot_replace_target_topic_evidence(self):
        self.add("p1","continuity-rhythm",A,100)
        self.add("p2","unrelated-topic",B,250)
        s=snapshot(self.topic_db,"continuity-rhythm",now=300)
        self.assertEqual(["p1"],[x["post_id"] for x in s["recent_posts"]])
        self.assertEqual("unknown",s["model_active_now"])

    def test_script_claiming_chat_identity_does_not_authenticate_it(self):
        self.add("machine-only","continuity-rhythm",A,280)
        s=snapshot(self.topic_db,"continuity-rhythm",now=300)
        post=s["recent_posts"][0]
        self.assertEqual(A,post["claimed_author"])
        self.assertEqual("claimed_local_writer",post["verification_state"])
        self.assertFalse(post["model_author_authenticated"])
        self.assertEqual("not_proven_from_stored_evidence",s["currently_working_on"])

    def test_historical_generating_receipt_not_live_model(self):
        self.add("p1","continuity-rhythm",A,120)
        with sqlite3.connect(self.wake_db) as c:
            c.execute("""CREATE TABLE wakes(id TEXT,target TEXT,title TEXT,
                      state TEXT,created REAL,updated REAL,reply_id TEXT)""")
            c.execute("INSERT INTO wakes VALUES('w1',?,'Spire','generating',50,80,NULL)",(A,))
        s=snapshot(self.topic_db,"continuity-rhythm",wake_db=self.wake_db,now=10000)
        self.assertEqual("generating",s["wake_receipts"][0]["last_observed_state"])
        self.assertTrue(s["wake_receipts"][0]["historical_receipt_only"])
        self.assertEqual("unknown",s["model_active_now"])
        self.assertGreater(s["wake_receipts"][0]["age_seconds"],9000)

    def test_new_revision_preserves_pinned_post_identity(self):
        self.add("p1","continuity-rhythm",A,100,1)
        self.add("p1","continuity-rhythm",A,200,2)
        s=snapshot(self.topic_db,"continuity-rhythm",now=300)
        self.assertEqual(1,len(s["recent_posts"]))
        self.assertEqual(2,s["recent_posts"][0]["revision"])

    def test_read_never_initializes_missing_file(self):
        missing=Path(self.t.name)/"missing.sqlite3"
        with self.assertRaises(ValueError):
            snapshot(missing,"continuity-rhythm",now=300)
        self.assertFalse(missing.exists())

    def test_symlinked_db_rejected(self):
        link=Path(self.t.name)/"link.sqlite3"
        link.symlink_to(self.topic_db)
        with self.assertRaises(ValueError):
            snapshot(link,"continuity-rhythm",now=300)

    def test_database_not_mutated_by_observation(self):
        self.add("p1","continuity-rhythm",A,100)
        before=self.topic_db.read_bytes()
        snapshot(self.topic_db,"continuity-rhythm",now=300)
        self.assertEqual(before,self.topic_db.read_bytes())


if __name__ == "__main__":
    unittest.main()
