"""Negative controls for distinct uses of one source by one downstream post.

Reference-only. A source receipt is not reviewer authorization or live wake.
"""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from baton_forum_reference import Forum

CHAT_A = "6aef3ac4-86bc-83ed-a4df-89e947bc5a34"
CHAT_B = "6aef341a-d850-83ed-a3b2-c735a215bce3"


class SourceUseTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        self.receipts = root / "receipts"
        self.receipts.mkdir()
        self.db = root / "forum.sqlite3"
        self.forum = Forum(self.db, self.receipts)
        self.forum.init()
        self.forum.create_topic("source", "Source")
        self.forum.create_topic("downstream", "Downstream")

    def post(self, topic, chat, number, body, *, kind="reply", reply_to=None):
        mid = f"00000000-0000-4000-8000-{number:012x}"
        url = "https://chatgpt.com/c/" + chat
        record = {
            "status": "reply_observed_in_exact_chat",
            "name": "Same alias for every post",
            "target_url": url,
            "return_id": mid,
            "return_text": body,
            "return_sha256": hashlib.sha256(body.encode()).hexdigest(),
            "independent_reload_verified": {
                "same_reply_id": True,
                "same_reply_sha256": True,
                "source_bound": True,
                "target_url": url,
            },
        }
        path = self.receipts / f"receipt-{number}.json"
        path.write_text(json.dumps(record), encoding="utf-8")
        return self.forum.ingest(topic, path, kind=kind, reply_to=reply_to)["id"]

    def fixture(self):
        a = self.post("source", CHAT_A, 1, "A original")
        b = self.post("downstream", CHAT_B, 2, "B uses A in two different ways")
        k = self.post("source", CHAT_A, 3, "A correction",
                      kind="correction", reply_to=a)
        r1 = self.post("source", CHAT_B, 4, "Reviewer 1 observation")
        r2 = self.post("source", CHAT_A, 5, "Reviewer 2 observation")
        return a,b,k,r1,r2

    def uses(self):
        return self.forum.show("downstream")["observations"][0]

    def test_same_a_to_b_two_distinct_uses_one_assessed(self):
        a,b,k,r1,_ = self.fixture()
        supporting = self.forum.add_dependency_use(
            b,a,use_key="support-alpha",use_mode="supports_claim",premise_key="alpha")
        fixture = self.forum.add_dependency_use(
            b,a,use_key="fixture-beta",use_mode="test_fixture",premise_key="beta")
        self.assertNotEqual(supporting,fixture)
        self.forum.record_use_assessment(k,supporting,"conflicts",r1)
        row = self.uses()
        self.assertEqual(row["depends_on"],[a])
        self.assertEqual(len(row["dependency_uses"]),2)
        by_key = {x["use_key"]:x for x in row["dependency_uses"]}
        self.assertEqual(by_key["support-alpha"]["correction_evaluations"][0]["verdict"],"conflicts")
        self.assertEqual(by_key["fixture-beta"]["correction_evaluations"][0]["verdict"],"unassessed")
        self.assertTrue(row["dependency_review_required"])
        self.assertTrue(row["dependency_impact_unassessed"])

    def test_identical_descriptors_do_not_collapse_occurrences(self):
        a,b,k,r1,r2 = self.fixture()
        x = self.forum.add_dependency_use(b,a,use_key="occurrence-one",
                                          use_mode="supports_claim",premise_key="same")
        y = self.forum.add_dependency_use(b,a,use_key="occurrence-two",
                                          use_mode="supports_claim",premise_key="same")
        self.forum.record_use_assessment(k,x,"conflicts",r1)
        self.forum.record_use_assessment(k,y,"unaffected",r2)
        found = {u["use_id"]:u for u in self.uses()["dependency_uses"]}
        self.assertEqual(found[x]["correction_evaluations"][0]["verdict"],"conflicts")
        self.assertEqual(found[y]["correction_evaluations"][0]["verdict"],"unaffected")
        self.assertFalse(self.uses()["dependency_assessment_disputed"])

    def test_use_key_replay_is_stable_and_reinterpretation_fails(self):
        a,b,k,r1,r2 = self.fixture()
        x = self.forum.add_dependency_use(b,a,use_key="occurrence-one",
                                          use_mode="supports_claim",premise_key="alpha")
        self.assertEqual(x,self.forum.add_dependency_use(
            b,a,use_key="occurrence-one",use_mode="supports_claim",premise_key="alpha"))
        for kwargs in (
            {"use_key":"occurrence-one","use_mode":"test_fixture","premise_key":"alpha"},
            {"use_key":"occurrence-one","use_mode":"supports_claim","premise_key":"beta"},
        ):
            with self.assertRaises(ValueError):
                self.forum.add_dependency_use(b,a,**kwargs)
        self.forum.init()
        self.assertEqual(x,self.forum.add_dependency_use(
            b,a,use_key="occurrence-one",use_mode="supports_claim",premise_key="alpha"))

    def test_legacy_assessment_not_migrated_into_new_uses(self):
        a,b,k,r1,r2 = self.fixture()
        self.forum.add_dependency(b,a,use_mode="supports_claim",premise_key="shared")
        self.forum.record_dependency_assessment(k,b,a,"conflicts",r1)
        u = self.forum.add_dependency_use(b,a,use_key="distinct-use",
                                          use_mode="supports_claim",premise_key="shared")
        found = self.uses()["dependency_uses"]
        self.assertEqual(len(found),2)
        legacy = next(x for x in found if x["use_id"] is None)
        modern = next(x for x in found if x["use_id"] == u)
        self.assertEqual(legacy["correction_evaluations"][0]["verdict"],"conflicts")
        self.assertEqual(modern["correction_evaluations"][0]["verdict"],"unassessed")
        self.forum.init()
        self.assertEqual(len(self.uses()["dependency_uses"]),2)

    def test_independent_opposed_assessments_same_use_preserved(self):
        a,b,k,r1,r2 = self.fixture()
        u = self.forum.add_dependency_use(b,a,use_key="support-alpha",
                                          use_mode="supports_claim",premise_key="alpha")
        self.forum.record_use_assessment(k,u,"conflicts",r1)
        self.forum.record_use_assessment(k,u,"unaffected",r2)
        self.forum.record_use_assessment(k,u,"conflicts",r1)
        row = self.uses()
        verdict = row["dependency_uses"][0]["correction_evaluations"][0]
        self.assertEqual(verdict["verdict"],"disputed")
        self.assertEqual([v["assessment_source_id"] for v in verdict["assessments"]],[r1,r2])
        self.assertTrue(row["dependency_assessment_disputed"])

    def test_wrong_correction_source_and_missing_evidence_rejected(self):
        a,b,k,r1,r2 = self.fixture()
        u = self.forum.add_dependency_use(b,a,use_key="support-alpha",
                                          use_mode="supports_claim",premise_key="alpha")
        other = self.post("source",CHAT_A,6,"Other original")
        wrong = self.post("source",CHAT_A,7,"Other correction",
                          kind="correction",reply_to=other)
        with self.assertRaises(ValueError):
            self.forum.record_use_assessment(wrong,u,"conflicts",r1)
        with self.assertRaises(ValueError):
            self.forum.record_use_assessment(k,u,"conflicts",999999)
        with self.assertRaises(ValueError):
            self.forum.record_use_assessment(k,999999,"conflicts",r1)
        self.assertEqual(self.uses()["dependency_uses"][0]["correction_evaluations"][0]["verdict"],
                         "unassessed")

    def test_same_evidence_cannot_silently_reverse_or_impersonate(self):
        a,b,k,r1,r2 = self.fixture()
        u = self.forum.add_dependency_use(b,a,use_key="support-alpha",
                                          use_mode="supports_claim",premise_key="alpha")
        self.forum.record_use_assessment(k,u,"conflicts",r1)
        with self.assertRaises(ValueError):
            self.forum.record_use_assessment(k,u,"unaffected",r1)
        # Different observation with identical alias is independent, not
        # authenticated proof that the original reviewer changed their mind.
        self.forum.record_use_assessment(k,u,"unaffected",r2)
        self.assertEqual(self.uses()["dependency_uses"][0]["correction_evaluations"][0]["verdict"],
                         "disputed")

    def test_concurrent_replay_allocates_only_one_use(self):
        a,b,k,r1,r2 = self.fixture()
        def attempt(_):
            return self.forum.add_dependency_use(b,a,use_key="stable-replay",
                use_mode="supports_claim",premise_key="alpha")
        with ThreadPoolExecutor(max_workers=4) as pool:
            ids = list(pool.map(attempt,range(8)))
        self.assertEqual(len(set(ids)),1)
        with sqlite3.connect(self.db) as c:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM dependency_use_instances").fetchone()[0],1)


if __name__ == "__main__":
    unittest.main()
