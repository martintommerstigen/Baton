"""Regression controls for legacy premise evidence versus assessed use edges.

A legacy (correction_id,premise_key) statement is NOT a verdict on each use.
This module tests a source-preserving migration without ChatGPT sends.
"""
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from baton_forum_reference import Forum

CHAT_A = "6aef3ac4-86bc-83ed-a4df-89e947bc5a34"
CHAT_B = "6aef341a-d850-83ed-a3b2-c735a215bce3"
CHAT_C = "6aef828e-0150-83eb-bbac-061f79a8fd4a"


class EdgeAssessmentTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.receipts = self.root / "receipts"
        self.receipts.mkdir()
        self.db = self.root / "forum.sqlite3"
        self.forum = Forum(self.db, self.receipts)
        self.forum.init()
        for topic in ("source", "downstream-b", "downstream-c"):
            self.forum.create_topic(topic, topic)

    def post(self, topic, chat, number, body, *, kind="reply", reply_to=None):
        mid = f"00000000-0000-4000-8000-{number:012x}"
        url = "https://chatgpt.com/c/" + chat
        doc = {
            "status": "reply_observed_in_exact_chat",
            "name": "Test participant",
            "target_url": url,
            "return_id": mid,
            "return_text": body,
            "return_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
            "independent_reload_verified": {
                "same_reply_id": True,
                "same_reply_sha256": True,
                "source_bound": True,
                "target_url": url,
            },
        }
        path = self.receipts / f"receipt-{number}.json"
        path.write_text(json.dumps(doc), encoding="utf-8")
        return self.forum.ingest(topic, path, kind=kind, reply_to=reply_to)["id"]

    def fixture(self):
        a = self.post("source", CHAT_A, 1, "Source A")
        b = self.post("downstream-b", CHAT_B, 2, "B uses A to support claim")
        c = self.post("downstream-c", CHAT_C, 3, "C retains A as a negative fixture")
        # Same literal premise and same use_mode: neither disambiguates the edge.
        self.forum.add_dependency(b, a, use_mode="supports_claim", premise_key="shared-premise")
        self.forum.add_dependency(c, a, use_mode="supports_claim", premise_key="shared-premise")
        k = self.post("source", CHAT_A, 4, "Correction K of A",
                      kind="correction", reply_to=a)
        reviewer = self.post("source", CHAT_B, 5, "Reviewer evidence for B")
        return a, b, c, k, reviewer

    def edge(self, topic):
        return self.forum.show(topic)["observations"][0]

    def test_legacy_row_never_becomes_two_edge_verdicts(self):
        a, b, c, k, reviewer = self.fixture()
        self.forum.record_impact(k, "shared-premise", "conflicts")
        for topic in ("downstream-b", "downstream-c"):
            observation = self.edge(topic)
            self.assertFalse(observation["dependency_review_required"])
            self.assertTrue(observation["dependency_impact_unassessed"])
            evaluation = observation["dependency_uses"][0]["correction_evaluations"][0]
            self.assertEqual(evaluation["verdict"], "unassessed")
            self.assertEqual(evaluation["legacy_unscoped_premise_assertion"], "conflicts")
            self.assertIsNone(evaluation["assessment_source_id"])
        self.forum.record_dependency_assessment(k, b, a, "conflicts", reviewer)
        self.assertTrue(self.edge("downstream-b")["dependency_review_required"])
        self.assertFalse(self.edge("downstream-b")["dependency_impact_unassessed"])
        self.assertFalse(self.edge("downstream-c")["dependency_review_required"])
        self.assertTrue(self.edge("downstream-c")["dependency_impact_unassessed"])

    def test_explicit_unaffected_for_c_does_not_change_b(self):
        a, b, c, k, reviewer = self.fixture()
        self.forum.record_dependency_assessment(k, b, a, "conflicts", reviewer)
        self.forum.record_dependency_assessment(k, c, a, "unaffected", reviewer)
        self.assertTrue(self.edge("downstream-b")["dependency_review_required"])
        self.assertFalse(self.edge("downstream-c")["dependency_review_required"])
        self.assertFalse(self.edge("downstream-c")["dependency_impact_unassessed"])

    def test_migration_preserves_legacy_rows_without_promoting_them(self):
        a, b, c, k, reviewer = self.fixture()
        self.forum.record_impact(k, "shared-premise", "conflicts")
        with sqlite3.connect(self.db) as conn:
            conn.execute("DROP TABLE dependency_assessments")
        self.forum.init()
        self.forum.init()  # Idempotent migration
        with sqlite3.connect(self.db) as conn:
            self.assertEqual(conn.execute(
                "SELECT count(*) FROM correction_impacts").fetchone()[0], 1)
            self.assertEqual(conn.execute(
                "SELECT count(*) FROM dependency_assessments").fetchone()[0], 0)
        self.assertTrue(self.edge("downstream-b")["dependency_impact_unassessed"])
        self.assertTrue(self.edge("downstream-c")["dependency_impact_unassessed"])

    def test_wrong_upstream_correction_rejected(self):
        a, b, c, k, reviewer = self.fixture()
        other = self.post("source", CHAT_A, 6, "Different source")
        self.forum.add_dependency(c, other, use_mode="supports_claim",
                                  premise_key="another-premise")
        with self.assertRaises(ValueError):
            self.forum.record_dependency_assessment(k, c, other, "conflicts", reviewer)

    def test_missing_edge_and_missing_evidence_rejected(self):
        a, b, c, k, reviewer = self.fixture()
        with self.assertRaises(ValueError):
            self.forum.record_dependency_assessment(k, reviewer, a, "conflicts", reviewer)
        with self.assertRaises(ValueError):
            self.forum.record_dependency_assessment(k, b, a, "conflicts", 999999)

    def test_edge_verdict_cannot_be_silently_replaced(self):
        a, b, c, k, reviewer = self.fixture()
        self.forum.record_dependency_assessment(k, b, a, "conflicts", reviewer)
        self.forum.record_dependency_assessment(k, b, a, "conflicts", reviewer)
        with self.assertRaises(ValueError):
            self.forum.record_dependency_assessment(k, b, a, "unaffected", reviewer)
        # A different observed source may independently agree; it must not
        # overwrite the first source or require a fictitious new correction.
        self.forum.record_dependency_assessment(k, b, a, "conflicts", k)
        evaluation = self.edge("downstream-b")["dependency_uses"][0]["correction_evaluations"][0]
        self.assertEqual(len(evaluation["assessments"]), 2)
        self.assertTrue(self.edge("downstream-b")["dependency_review_required"])


    def test_opposed_assessments_are_order_independent_and_visible(self):
        results = []
        for idx, order in enumerate(((("conflicts", 5), ("unaffected", 6)),
                                     (("unaffected", 6), ("conflicts", 5)))):
            # Independent databases: insertion order is the ONLY changed input.
            self.forum = Forum(self.root / f"case-{idx}.sqlite3", self.receipts)
            self.forum.init()
            for topic in ("source", "downstream-b", "downstream-c"):
                self.forum.create_topic(topic, topic)
            a, b, c, k, reviewer1 = self.fixture()
            reviewer2 = self.post("source", CHAT_C, 6, "Independent review of same edge")
            for verdict, source_number in order:
                source = reviewer1 if source_number == 5 else reviewer2
                self.forum.record_dependency_assessment(k, b, a, verdict, source)
            observation = self.edge("downstream-b")
            evaluation = observation["dependency_uses"][0]["correction_evaluations"][0]
            self.assertEqual(evaluation["verdict"], "disputed")
            self.assertTrue(evaluation["disputed"])
            self.assertIsNone(evaluation["assessment_source_id"])
            self.assertTrue(observation["dependency_assessment_disputed"])
            self.assertTrue(observation["dependency_review_required"])
            self.assertFalse(observation["dependency_impact_unassessed"])
            self.assertFalse(self.edge("downstream-c")["dependency_assessment_disputed"])
            results.append((evaluation["assessments"], evaluation["verdict"],
                            observation["dependency_assessment_disputed"],
                            observation["dependency_review_required"]))
        self.assertEqual(results[0], results[1])
        self.assertEqual(results[0][0], [
            {"assessment_source_id": 5, "verdict": "conflicts"},
            {"assessment_source_id": 6, "verdict": "unaffected"}])

    def test_independent_agreement_preserves_both_sources_and_replay(self):
        a, b, c, k, reviewer1 = self.fixture()
        reviewer2 = self.post("source", CHAT_C, 6, "Independent corroboration")
        self.forum.record_dependency_assessment(k, b, a, "conflicts", reviewer2)
        self.forum.record_dependency_assessment(k, b, a, "conflicts", reviewer1)
        self.forum.record_dependency_assessment(k, b, a, "conflicts", reviewer1)
        observation = self.edge("downstream-b")
        evaluation = observation["dependency_uses"][0]["correction_evaluations"][0]
        self.assertEqual(evaluation["verdict"], "conflicts")
        self.assertFalse(evaluation["disputed"])
        self.assertEqual(evaluation["assessments"], [
            {"assessment_source_id": reviewer1, "verdict": "conflicts"},
            {"assessment_source_id": reviewer2, "verdict": "conflicts"}])
        with self.assertRaises(ValueError):
            self.forum.record_dependency_assessment(k, b, a, "unaffected", reviewer1)
        self.assertEqual(len(self.edge("downstream-b")["dependency_uses"][0]
                             ["correction_evaluations"][0]["assessments"]), 2)

    def test_preexisting_single_edge_assessment_survives_additive_migration(self):
        a, b, c, k, reviewer1 = self.fixture()
        with sqlite3.connect(self.db) as conn:
            conn.execute("""INSERT INTO dependency_assessments
                (correction_id,downstream_id,upstream_id,verdict,assessment_source_id)
                VALUES(?,?,?,?,?)""", (k, b, a, "conflicts", reviewer1))
            conn.execute("DROP TABLE dependency_assessment_events")
        self.forum.init()
        self.forum.init()
        reviewer2 = self.post("source", CHAT_C, 6, "Contrary independent review")
        self.forum.record_dependency_assessment(k, b, a, "unaffected", reviewer2)
        # The original PR #92 row stays in its original table, unmodified.
        with sqlite3.connect(self.db) as conn:
            self.assertEqual(conn.execute(
                "SELECT verdict,assessment_source_id FROM dependency_assessments"
            ).fetchall(), [("conflicts", reviewer1)])
            self.assertEqual(conn.execute(
                "SELECT verdict,assessment_source_id FROM dependency_assessment_events"
            ).fetchall(), [("unaffected", reviewer2)])
        evaluation = self.edge("downstream-b")["dependency_uses"][0]["correction_evaluations"][0]
        self.assertEqual(evaluation["verdict"], "disputed")
        self.assertEqual(len(evaluation["assessments"]), 2)
        self.forum.record_dependency_assessment(k, b, a, "conflicts", reviewer1)
        self.assertEqual(len(self.edge("downstream-b")["dependency_uses"][0]
                             ["correction_evaluations"][0]["assessments"]), 2)

    def test_unknown_source_does_not_hide_explicit_conflict(self):
        a, b, c, k, reviewer1 = self.fixture()
        reviewer2 = self.post("source", CHAT_C, 6, "Unknown impact")
        self.forum.record_dependency_assessment(k, b, a, "unknown", reviewer2)
        self.forum.record_dependency_assessment(k, b, a, "conflicts", reviewer1)
        observation = self.edge("downstream-b")
        evaluation = observation["dependency_uses"][0]["correction_evaluations"][0]
        self.assertEqual(evaluation["verdict"], "conflicts")
        self.assertFalse(evaluation["disputed"])
        self.assertTrue(observation["dependency_review_required"])
        self.assertTrue(observation["dependency_impact_unassessed"])


if __name__ == "__main__":
    unittest.main()
