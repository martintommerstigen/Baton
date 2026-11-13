"""Source-bound negative controls for corrections to corrections.

A correction to a correction must remain visible to downstream readers.
It is NOT automatically a retraction, permission revocation, or new verdict.
Synthetic receipts only; no browser send or ChatGPT wake.
"""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from uuid import uuid4

from baton_forum_reference import Forum

CHATS = (
    "6aef3ac4-86bc-83ed-a4df-89e947bc5a34",
    "6aef341a-d850-83ed-a3b2-c735a215bce3",
    "6aee69e6-21ec-83eb-8b0e-ab43497695b0",
)


class CorrectionLineageTests(unittest.TestCase):
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
        receipt = {
            "status": "reply_observed_in_exact_chat",
            "name": "synthetic-lineage-fixture",
            "target_url": target,
            "return_id": mid,
            "return_text": body,
            "return_sha256": hashlib.sha256(body.encode()).hexdigest(),
            "independent_reload_verified": {
                "same_reply_id": True,
                "same_reply_sha256": True,
                "source_bound": True,
                "target_url": target,
            },
        }
        path = self.receipts / (mid + ".json")
        path.write_text(json.dumps(receipt), encoding="utf-8")
        return self.forum.ingest(topic, path, kind=kind, reply_to=reply_to)["id"]

    def observed(self, topic, obs_id):
        return next(o for o in self.forum.show(topic)["observations"] if o["id"] == obs_id)

    def test_correction_of_correction_visible_without_erasing_old_verdict(self):
        a = self.post("source", "A: premise")
        b = self.post("middle", "B uses A", chat=1)
        self.forum.add_dependency(b, a, use_mode="supports_claim", premise_key="premise-one")
        first = self.post("source", "A1: premise is wrong", kind="correction", reply_to=a)
        self.forum.record_impact(first, "premise-one", "conflicts")
        before = self.observed("middle", b)
        self.assertEqual(before["source_correction_ids"], [first])
        self.assertEqual(before["correction_followup_ids"], [])
        self.assertTrue(before["dependency_review_required"])

        second = self.post("source", "A2: A1 was too strong", kind="correction", reply_to=first)
        self.forum.record_impact(second, "premise-one", "unaffected")
        after = self.observed("middle", b)
        self.assertEqual(after["source_correction_ids"], [first])
        self.assertEqual(after["correction_followup_ids"], [second])
        self.assertTrue(after["correction_lineage_has_followups"])
        # A2 is visible, but its semantics cannot silently overwrite A1.
        self.assertTrue(after["dependency_review_required"])
        self.assertEqual(after["body"], "B uses A")

    def test_multilevel_followups_and_unrelated_topic_are_separate(self):
        a = self.post("source", "A")
        b = self.post("middle", "B", chat=1)
        d = self.post("unrelated", "D", chat=2)
        self.forum.add_dependency(b, a)
        first = self.post("source", "A1", kind="correction", reply_to=a)
        second = self.post("source", "A2", kind="correction", reply_to=first)
        third = self.post("source", "A3", kind="correction", reply_to=second)
        result = self.observed("middle", b)
        self.assertEqual(result["correction_followup_ids"], [second, third])
        self.assertFalse(result["dependency_review_required"])
        self.assertFalse(self.observed("unrelated", d)["correction_lineage_has_followups"])

    def test_plain_reply_to_correction_is_not_another_correction(self):
        a = self.post("source", "A")
        b = self.post("middle", "B", chat=1)
        self.forum.add_dependency(b, a)
        first = self.post("source", "A1", kind="correction", reply_to=a)
        self.post("source", "Thanks for A1", kind="reply", reply_to=first)
        result = self.observed("middle", b)
        self.assertEqual(result["source_correction_ids"], [first])
        self.assertEqual(result["correction_followup_ids"], [])

    def test_indirect_reader_sees_correction_lineage_without_global_stop(self):
        a = self.post("source", "A")
        b = self.post("middle", "B", chat=1)
        c = self.post("downstream", "C", chat=2)
        self.forum.add_dependency(b, a, use_mode="test_fixture", premise_key="fixture-one")
        self.forum.add_dependency(c, b, use_mode="supports_claim", premise_key="premise-two")
        first = self.post("source", "A1", kind="correction", reply_to=a)
        second = self.post("source", "A2", kind="correction", reply_to=first)
        result = self.observed("downstream", c)
        self.assertEqual(result["indirect_source_correction_ids"], [first])
        self.assertEqual(result["correction_followup_ids"], [second])
        self.assertFalse(result["dependency_review_required"])


if __name__ == "__main__":
    unittest.main()
