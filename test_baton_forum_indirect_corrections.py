"""Negative controls for indirect source corrections in the isolated Baton forum.

Synthetic receipts only: these tests never wake a ChatGPT conversation or
authorize an action. Indirect evidence must be visible without silently
declaring a downstream claim false or stopping unrelated work.
"""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from uuid import uuid4

from baton_forum_reference import Forum


CHATS = [
    "6aef3ac4-86bc-83ed-a4df-89e947bc5a34",
    "6aef341a-d850-83ed-a3b2-c735a215bce3",
    "6aee69e6-21ec-83eb-8b0e-ab43497695b0",
]


class IndirectCorrectionTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        self.receipts = root / "receipts"
        self.receipts.mkdir()
        self.forum = Forum(root / "forum.sqlite3", self.receipts)
        self.forum.init()
        for topic in ("source", "middle", "downstream", "unrelated"):
            self.forum.create_topic(topic, topic + " topic")

    def post(self, topic, body, *, chat=0, kind="reply", reply_to=None):
        mid = str(uuid4())
        target = "https://chatgpt.com/c/" + CHATS[chat]
        data = {
            "status": "reply_observed_in_exact_chat",
            "name": "synthetic-test-source",
            "target_url": target,
            "return_id": mid,
            "return_text": body,
            "return_sha256": hashlib.sha256(body.encode()).hexdigest(),
            "independent_reload_verified": {
                "same_reply_id": True, "same_reply_sha256": True,
                "source_bound": True, "target_url": target
            },
        }
        path = self.receipts / (mid + ".json")
        path.write_text(json.dumps(data), encoding="utf-8")
        return self.forum.ingest(topic, path, kind=kind, reply_to=reply_to)["id"]

    def observation(self, topic, obs_id):
        return next(o for o in self.forum.show(topic)["observations"] if o["id"] == obs_id)

    def test_three_topic_correction_reaches_indirect_reader_without_false_verdict(self):
        a = self.post("source", "A: original premise")
        b = self.post("middle", "B: claim using A", chat=1)
        c = self.post("downstream", "C: claim using B", chat=2)
        independent = self.post("unrelated", "D: independent")
        self.forum.add_dependency(b, a, use_mode="supports_claim", premise_key="premise-one")
        self.forum.add_dependency(c, b, use_mode="supports_claim", premise_key="premise-two")
        self.assertEqual(self.observation("downstream", c)["indirect_source_correction_ids"], [])
        correction = self.post("source", "A is corrected", kind="correction", reply_to=a)
        self.forum.record_impact(correction, "premise-one", "conflicts")

        middle = self.observation("middle", b)
        self.assertTrue(middle["dependency_review_required"])
        downstream = self.observation("downstream", c)
        self.assertEqual(downstream["indirect_source_correction_ids"], [correction])
        self.assertTrue(downstream["indirect_source_change_unassessed"])
        self.assertFalse(downstream["dependency_review_required"])
        self.assertFalse(downstream["dependency_impact_unassessed"])
        self.assertEqual(downstream["body"], "C: claim using B")
        self.assertFalse(self.observation("unrelated", independent)["indirect_source_change_unassessed"])

    def test_unaffected_fixture_does_not_become_global_stop(self):
        a = self.post("source", "A: isolated fixture")
        b = self.post("middle", "B: negative test fixture", chat=1)
        c = self.post("downstream", "C: references B", chat=2)
        self.forum.add_dependency(b, a, use_mode="test_fixture", premise_key="fixture-only")
        self.forum.add_dependency(c, b, use_mode="supports_claim", premise_key="fixture-used")
        correction = self.post("source", "A corrected outside fixture", kind="correction", reply_to=a)
        self.forum.record_impact(correction, "fixture-only", "unaffected")
        self.assertFalse(self.observation("middle", b)["dependency_review_required"])
        downstream = self.observation("downstream", c)
        self.assertEqual(downstream["indirect_source_correction_ids"], [correction])
        self.assertFalse(downstream["dependency_review_required"])

    def test_cyclic_reference_graph_terminates_without_inventing_impact(self):
        a = self.post("source", "A")
        b = self.post("middle", "B", chat=1)
        c = self.post("downstream", "C", chat=2)
        self.forum.add_dependency(b, a)
        self.forum.add_dependency(c, b)
        self.forum.add_dependency(a, c)
        correction = self.post("source", "Correction of A", kind="correction", reply_to=a)
        result = self.observation("downstream", c)
        self.assertEqual(result["indirect_source_correction_ids"], [correction])
        self.assertFalse(result["dependency_review_required"])


if __name__ == "__main__":
    unittest.main()
