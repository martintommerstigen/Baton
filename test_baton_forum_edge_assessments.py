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
        with self.assertRaises(ValueError):
            self.forum.record_dependency_assessment(k, b, a, "conflicts", k)
        self.assertTrue(self.edge("downstream-b")["dependency_review_required"])


if __name__ == "__main__":
    unittest.main()
