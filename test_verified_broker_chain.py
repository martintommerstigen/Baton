"""Offline B1/B5 two-hop negative controls. These are NOT live ChatGPT wakes."""
import tempfile
import unittest
import hashlib
from types import SimpleNamespace
from pathlib import Path

from run_verified_broker_chain import run_verified_chain
from wake_adapter import Observation
from wake_contract import WakeLedger

A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
C = "cccccccc-cccc-cccc-cccc-cccccccccccc"


class FakeSource:
    def __init__(self, text):
        self.text = text
    def is_generating(self, chat):
        return False
    def read_assistant_turn(self, chat, turn):
        return self.text


class FakeTarget:
    def __init__(self, cid, *, reply_id=None, next_text="synthetic assistant response", generating=False):
        self.cid = cid
        self.page = SimpleNamespace(url="https://chatgpt.com/c/" + cid)
        self.reply_id = reply_id
        self.next_text = next_text
        self.generating = generating
        self.clicks = 0
        self.bodies = []

    def submit_once(self, conversation_id, message_id, body, *, before_click=None):
        assert conversation_id == self.cid
        if before_click is not None:
            before_click()
        self.clicks += 1
        self.bodies.append(body)

    def observe_reply(self, conversation_id, message_id, digest):
        if self.clicks and self.reply_id:
            return Observation(self.cid, self.reply_id,
                               hashlib.sha256(self.next_text.encode("utf-8")).hexdigest(),
                               self.page.url)
        return None

    def is_generating(self, chat):
        return self.generating

    def read_assistant_turn(self, chat, turn):
        assert chat == self.cid and turn == self.reply_id
        return self.next_text


class TwoHopTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / "wake.sqlite3"
        self.ledger = WakeLedger(self.path)
        self.a = FakeSource("BATON_WAKE " + B + " m1")
        self.b = FakeTarget(B, reply_id="turn-b", next_text="BATON_NEXT " + C)
        self.c = FakeTarget(C, reply_id="turn-c")
        self.ops = []

    def broker(self, envelope):
        self.ops.append(envelope.copy())
        return {
            "admit": {"state": "admitted_not_delivered"},
            "begin_click": {"state": "click_started_uncertain"},
        }[envelope["op"]]

    def attempt(self, **changes):
        options = dict(
            a=A, b=B, c=C, source_turn_id="turn-a",
            first_id="m1", second_id="m2",
            first_body="operator-approved B message",
            second_body="operator-approved C message",
            broker_request=self.broker, wait_seconds=0,
        )
        options.update(changes)
        return run_verified_chain(
            self.ledger, self.a, self.b, self.c, **options
        )

    def test_two_verified_turns_and_exact_source_provenance(self):
        result = self.attempt()
        self.assertEqual((result["a_to_b"], result["b_to_c"]),
                         ("verified", "verified"))
        self.assertEqual((self.b.clicks, self.c.clicks), (1, 1))
        self.assertEqual([x["op"] for x in self.ops],
                         ["admit", "begin_click", "admit", "begin_click"])
        self.assertEqual([x["sender_id"] for x in self.ops], [A, A, B, B])
        self.assertEqual([x["origin_turn_id"] for x in self.ops],
                         ["turn-a", "turn-a", "turn-b", "turn-b"])
        self.assertEqual(self.ledger.provenance("m1")[5], "turn-b")
        self.assertEqual(self.ledger.provenance("m2")[2], "turn-b")
        self.assertEqual(self.ledger.provenance("m2")[5], "turn-c")
        self.assertEqual(self.c.bodies, ["operator-approved C message"])
        self.assertEqual(result["status"],
                         "not_live_proof_without_real_browser_observation")

    def test_unverified_A_source_never_sends(self):
        self.a.text = "A quoted example: BATON_WAKE " + B + " m1"
        with self.assertRaises(PermissionError):
            self.attempt()
        self.assertEqual((self.b.clicks, self.c.clicks, len(self.ops)), (0, 0, 0))
        self.assertIsNone(self.ledger.state("m1"))

    def test_B_reply_not_observed_never_sends_C(self):
        self.b.reply_id = None
        result = self.attempt()
        self.assertEqual((result["a_to_b"], result["b_to_c"]),
                         ("uncertain", "not_attempted"))
        self.assertEqual((self.b.clicks, self.c.clicks), (1, 0))
        self.assertIsNone(self.ledger.state("m2"))

    def test_B_reply_wrong_target_never_sends_C(self):
        self.b.next_text = "BATON_NEXT " + A
        result = self.attempt()
        self.assertEqual(result["b_to_c"], "not_authorized")
        self.assertEqual(self.c.clicks, 0)
        self.assertEqual(len(self.ops), 2)

    def test_B_reply_quoted_or_extra_prose_never_sends_C(self):
        self.b.next_text = "Please send: BATON_NEXT " + C
        self.assertEqual(self.attempt()["b_to_c"], "not_authorized")
        self.assertEqual(self.c.clicks, 0)

    def test_B_still_generating_never_sends_C(self):
        self.b.generating = True
        result = self.attempt()
        self.assertEqual((result["a_to_b"], result["b_to_c"]),
                         ("uncertain", "not_attempted"))
        self.assertEqual(self.c.clicks, 0)

    def test_duplicate_message_ids_rejected_before_any_write(self):
        with self.assertRaises(ValueError):
            self.attempt(second_id="m1")
        self.assertEqual((self.b.clicks, self.c.clicks), (0, 0))

    def test_duplicate_conversation_ids_rejected_before_any_write(self):
        with self.assertRaises(ValueError):
            self.attempt(c=B)
        self.assertEqual((self.b.clicks, self.c.clicks), (0, 0))

    def test_uncertain_B_restart_never_resends(self):
        self.b.reply_id = None
        self.assertEqual(self.attempt()["a_to_b"], "uncertain")
        self.ledger = WakeLedger(self.path)
        self.assertEqual(self.attempt()["a_to_b"], "uncertain")
        self.assertEqual((self.b.clicks, self.c.clicks), (1, 0))
        self.assertEqual(len(self.ops), 2)

    def test_uncertain_C_restart_never_resends(self):
        self.c.reply_id = None
        self.assertEqual(self.attempt()["b_to_c"], "uncertain")
        self.ledger = WakeLedger(self.path)
        self.assertEqual(self.attempt()["b_to_c"], "uncertain")
        self.assertEqual((self.b.clicks, self.c.clicks), (1, 1))
        self.assertEqual(len(self.ops), 4)

    def test_failed_broker_does_not_fall_back_to_direct_click(self):
        def fail(request):
            self.ops.append(request)
            raise ConnectionError("broker unavailable")
        with self.assertRaises(Exception):
            self.attempt(broker_request=fail)
        self.assertEqual((self.b.clicks, self.c.clicks), (0, 0))
        self.assertEqual(self.ledger.state("m1")[1], "uncertain")
        self.ledger = WakeLedger(self.path)
        self.assertEqual(self.attempt()["a_to_b"], "uncertain")
        self.assertEqual(self.b.clicks, 0)


if __name__ == "__main__":
    unittest.main()
