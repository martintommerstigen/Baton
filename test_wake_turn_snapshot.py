"""B1 first-observation digest negatives. Offline fake DOM; not a live wake."""
import hashlib
import tempfile
import unittest
from pathlib import Path

import test_verified_broker_chain as base
from run_verified_broker_chain import run_verified_chain
from wake_adapter import Observation
from wake_contract import WakeLedger
from wake_turn_snapshot import (
    SourceEvidenceChanged, TurnSnapshotStore, verify_current_b_turn,
    verify_current_reply,
)


class ObservedTurnDigestTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.db = Path(temp.name) / "wake.sqlite3"
        self.ledger = WakeLedger(self.db)
        self.a = base.FakeSource("BATON_WAKE " + base.B + " m1")
        self.b = base.FakeTarget(base.B, reply_id="turn-b",
                                 next_text="BATON_NEXT " + base.C)
        self.c = base.FakeTarget(base.C, reply_id="turn-c")
        self.ops = []

    def broker(self, envelope):
        self.ops.append(envelope.copy())
        return {
            "admit": {"state": "admitted_not_delivered"},
            "begin_click": {"state": "click_started_uncertain"},
        }[envelope["op"]]

    def run_chain(self, broker=None):
        return run_verified_chain(
            self.ledger, self.a, self.b, self.c,
            a=base.A, b=base.B, c=base.C,
            source_turn_id="turn-a", first_id="m1", second_id="m2",
            first_body="preapproved B", second_body="preapproved C",
            broker_request=broker or self.broker, wait_seconds=0,
        )

    def test_first_observed_text_digest_is_durable_without_raw_text(self):
        result = self.run_chain()
        self.assertEqual((result["a_to_b"], result["b_to_c"]),
                         ("verified", "verified"))
        snap = TurnSnapshotStore(self.ledger).get("m1")
        self.assertEqual(snap.text_sha256,
                         hashlib.sha256(("BATON_NEXT " + base.C).encode()).hexdigest())
        self.assertEqual(snap.turn_id, "turn-b")
        self.assertEqual(snap.source_url, "https://chatgpt.com/c/" + base.B)
        self.assertNotIn("BATON_NEXT", repr(snap))
        self.ledger = WakeLedger(self.db)
        self.assertEqual(verify_current_b_turn(
            self.ledger, TurnSnapshotStore(self.ledger), self.b,
            "m1", base.B, base.C), snap)

    def test_same_turn_mutates_between_observe_and_snapshot(self):
        self.b.next_text = "ordinary response"
        original = self.b.observe_reply
        def change_after_observation(*args):
            obs = original(*args)
            self.b.next_text = "BATON_NEXT " + base.C
            return obs
        self.b.observe_reply = change_after_observation
        with self.assertRaises(SourceEvidenceChanged):
            self.run_chain()
        self.assertEqual(self.ledger.state("m1")[1], "uncertain")
        self.assertEqual(self.c.clicks, 0)
        self.assertIsNone(TurnSnapshotStore(self.ledger).get("m1"))

    def test_same_turn_mutates_after_snapshot_before_authorization(self):
        original = self.b.read_assistant_turn
        calls = [0]
        def mutate_on_second_read(*args):
            calls[0] += 1
            if calls[0] == 2:
                self.b.next_text = "BATON_NEXT " + base.A
            return original(*args)
        self.b.read_assistant_turn = mutate_on_second_read
        result = self.run_chain()
        self.assertEqual((result["a_to_b"], result["b_to_c"]),
                         ("verified", "not_authorized"))
        self.assertEqual(self.c.clicks, 0)
        self.assertEqual([r["op"] for r in self.ops], ["admit", "begin_click"])

    def test_same_turn_mutates_during_c_admit(self):
        def mutate(request):
            answer = self.broker(request)
            if request["sender_id"] == base.B and request["op"] == "admit":
                self.b.next_text = "BATON_NEXT " + base.A
            return answer
        with self.assertRaises(Exception):
            self.run_chain(mutate)
        self.assertEqual(self.c.clicks, 0)
        self.assertEqual(self.ledger.state("m2")[1], "uncertain")

    def test_same_turn_mutates_after_durable_c_begin(self):
        def mutate(request):
            answer = self.broker(request)
            if request["sender_id"] == base.B and request["op"] == "begin_click":
                self.b.next_text = "BATON_NEXT " + base.A
            return answer
        with self.assertRaises(Exception):
            self.run_chain(mutate)
        self.assertEqual(self.c.clicks, 0)
        self.assertEqual(self.ledger.state("m2")[1], "uncertain")
        self.b.next_text = "BATON_NEXT " + base.C
        self.ledger = WakeLedger(self.db)
        before = len(self.ops)
        self.assertEqual(self.run_chain()["b_to_c"], "uncertain")
        self.assertEqual(len(self.ops), before)
        self.assertEqual(self.c.clicks, 0)

    def test_source_url_changes_during_c_admit(self):
        def mutate(request):
            answer = self.broker(request)
            if request["sender_id"] == base.B and request["op"] == "admit":
                self.b.page.url = "https://chatgpt.com/c/" + base.A
            return answer
        with self.assertRaises(Exception):
            self.run_chain(mutate)
        self.assertEqual(self.c.clicks, 0)
        self.assertEqual(self.ledger.state("m2")[1], "uncertain")

    def test_missing_observation_digest_rejected(self):
        original = self.b.observe_reply
        def missing(*args):
            obs = original(*args)
            return Observation(obs.conversation_id, obs.assistant_turn_id)
        self.b.observe_reply = missing
        with self.assertRaises(SourceEvidenceChanged):
            self.run_chain()
        self.assertEqual(self.c.clicks, 0)

    def test_deleted_snapshot_on_restart_cannot_authorize_new_c(self):
        result = self.run_chain()
        self.assertEqual(result["b_to_c"], "verified")
        with self.ledger.db() as db:
            db.execute("DELETE FROM wake_turn_snapshots WHERE message_id='m1'")
        self.ledger = WakeLedger(self.db)
        before = len(self.ops)
        result = self.run_chain()
        self.assertEqual(result["b_to_c"], "not_authorized")
        self.assertEqual(self.c.clicks, 1)
        self.assertEqual(len(self.ops), before)

    def test_c_reply_snapshot_is_durable_and_read_only_rechecked(self):
        result = self.run_chain()
        self.assertEqual(result["b_to_c"], "verified")
        snap = TurnSnapshotStore(self.ledger).get("m2")
        self.assertEqual(snap.chat, base.C)
        self.assertEqual(snap.turn_id, "turn-c")
        self.assertEqual(snap.text_sha256,
                         hashlib.sha256(self.c.next_text.encode()).hexdigest())
        self.assertEqual(result["c_reply_snapshot"]["text_sha256"], snap.text_sha256)
        self.ledger = WakeLedger(self.db)
        self.assertEqual(verify_current_reply(
            self.ledger, TurnSnapshotStore(self.ledger), self.c, "m2", base.C), snap)

    def test_c_reply_changes_after_observation_before_snapshot(self):
        original = self.c.observe_reply
        def mutate_after_observe(*args):
            obs = original(*args)
            self.c.next_text = "changed C text, same DOM turn"
            return obs
        self.c.observe_reply = mutate_after_observe
        with self.assertRaises(SourceEvidenceChanged):
            self.run_chain()
        self.assertEqual(self.ledger.state("m2")[1], "uncertain")
        self.assertIsNone(TurnSnapshotStore(self.ledger).get("m2"))
        self.assertEqual(self.c.clicks, 1)
        self.ledger = WakeLedger(self.db)
        self.assertEqual(self.run_chain()["b_to_c"], "uncertain")
        self.assertEqual(self.c.clicks, 1)

    def test_c_reply_changes_after_snapshot_before_final_readback(self):
        original = self.c.read_assistant_turn
        count = [0]
        def mutate_on_final_read(*args):
            count[0] += 1
            if count[0] == 2:
                self.c.next_text = "C reply mutated after durable snapshot"
            return original(*args)
        self.c.read_assistant_turn = mutate_on_final_read
        with self.assertRaises(SourceEvidenceChanged):
            self.run_chain()
        # Delivery may have happened; never resubmit. A verified ledger
        # alone is insufficient to certify the final C content.
        self.assertEqual(self.ledger.state("m2")[1], "verified")
        self.assertEqual(self.c.clicks, 1)
        with self.assertRaises(SourceEvidenceChanged):
            verify_current_reply(self.ledger, TurnSnapshotStore(self.ledger),
                                 self.c, "m2", base.C)

    def test_empty_c_assistant_reply_is_not_verified(self):
        self.c.next_text = ""
        with self.assertRaises(SourceEvidenceChanged):
            self.run_chain()
        self.assertEqual(self.ledger.state("m2")[1], "uncertain")
        self.assertEqual(self.c.clicks, 1)

    def test_b_source_mutates_during_c_click_and_stays_invalid_after_restore(self):
        # Earlier B checks all pass; C's click then changes the same B turn.
        # The old runner would have reported two verified hops and C snapshot.
        original_submit = self.c.submit_once
        def change_b_after_c_click(*args, **kwargs):
            original_submit(*args, **kwargs)
            self.b.next_text = "BATON_NEXT " + base.A
        self.c.submit_once = change_b_after_c_click
        with self.assertRaises(SourceEvidenceChanged):
            self.run_chain()
        self.assertEqual((self.b.clicks, self.c.clicks), (1, 1))
        self.assertEqual(self.ledger.state("m2")[1], "verified")
        self.assertIsNotNone(TurnSnapshotStore(self.ledger).get("m2"))
        self.assertEqual(len(self.ops), 4)
        with self.assertRaises(SourceEvidenceChanged):
            TurnSnapshotStore(self.ledger).assert_chain_not_invalidated("m2")

        # Restoring the DOM must not erase a witnessed contradiction.
        self.b.next_text = "BATON_NEXT " + base.C
        self.ledger = WakeLedger(self.db)
        with self.assertRaises(SourceEvidenceChanged):
            self.run_chain()
        self.assertEqual((self.b.clicks, self.c.clicks), (1, 1))
        self.assertEqual(len(self.ops), 4)

    def test_c_source_mutation_after_snapshot_invalidates_chain_on_restart(self):
        original_read = self.c.read_assistant_turn
        calls = [0]
        def mutate_c_on_final_read(*args):
            calls[0] += 1
            if calls[0] == 2:
                self.c.next_text = "changed C reply"
            return original_read(*args)
        self.c.read_assistant_turn = mutate_c_on_final_read
        with self.assertRaises(SourceEvidenceChanged):
            self.run_chain()
        self.assertEqual(self.ledger.state("m2")[1], "verified")
        self.c.next_text = "synthetic assistant response"
        self.ledger = WakeLedger(self.db)
        with self.assertRaises(SourceEvidenceChanged):
            self.run_chain()
        self.assertEqual((self.b.clicks, self.c.clicks), (1, 1))
        self.assertEqual(len(self.ops), 4)


if __name__ == "__main__":
    unittest.main()
