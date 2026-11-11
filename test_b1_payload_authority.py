"""B1 digest-bound existing-chat source authorization; offline fakes only.

The verified live CLI requires exact A and B assistant-turn commitments to
operator-approved payload SHA-256. These tests do not claim live ChatGPT wake.
"""
import hashlib
import tempfile
import unittest
from pathlib import Path

from inspect_b1_readiness import inspect_boundary
from run_verified_broker_chain import run_verified_chain
from test_inspect_b1_readiness import Browser, Driver, Page, A, B, C
from test_verified_broker_chain import FakeSource, FakeTarget
from wake_chain import next_target_from_reply
from wake_contract import WakeLedger
from wake_origin import source_requested_wake


def digest(body):
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


class DigestBoundSourceTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.db = Path(tmp.name) / "wake.sqlite3"
        self.ledger = WakeLedger(self.db)
        self.first_body = "approved challenge for B"
        self.second_body = "approved challenge for C"
        self.a = FakeSource(self.a_command())
        self.b = FakeTarget(B, reply_id="turn-b", next_text=self.b_command())
        self.c = FakeTarget(C, reply_id="turn-c")
        self.ops = []

    def a_command(self, body=None):
        return "BATON_WAKE " + B + " m1 sha256:" + digest(
            self.first_body if body is None else body)

    def b_command(self, body=None):
        return "BATON_NEXT " + C + " sha256:" + digest(
            self.second_body if body is None else body)

    def broker(self, envelope):
        self.ops.append(envelope.copy())
        return {"admit": {"state": "admitted_not_delivered"},
                "begin_click": {"state": "click_started_uncertain"}}[envelope["op"]]

    def run(self):
        return run_verified_chain(
            self.ledger, self.a, self.b, self.c,
            a=A, b=B, c=C, source_turn_id="turn-a",
            first_id="m1", second_id="m2",
            first_body=self.first_body, second_body=self.second_body,
            broker_request=self.broker, wait_seconds=0,
            require_payload_authority=True,
        )

    def test_both_exact_commitments_authorize_two_hops(self):
        result = self.run()
        self.assertEqual((result["a_to_b"], result["b_to_c"]),
                         ("verified", "verified"))
        self.assertEqual((self.b.clicks, self.c.clicks), (1, 1))
        self.assertEqual(len(self.ops), 4)
        self.assertEqual(self.ledger.provenance("m1")[3], digest(self.first_body))
        self.assertEqual(self.ledger.provenance("m2")[3], digest(self.second_body))

    def test_legacy_a_command_does_not_authorize_any_send(self):
        self.a.text = "BATON_WAKE " + B + " m1"
        with self.assertRaises(PermissionError):
            self.run()
        self.assertEqual((self.b.clicks, self.c.clicks, len(self.ops)), (0, 0, 0))
        self.assertIsNone(self.ledger.state("m1"))

    def test_same_a_command_with_different_body_is_rejected(self):
        self.first_body = "different body, same A source turn"
        with self.assertRaises(PermissionError):
            self.run()
        self.assertEqual((self.b.clicks, len(self.ops)), (0, 0))

    def test_legacy_b_command_cannot_authorize_c(self):
        self.b.next_text = "BATON_NEXT " + C
        result = self.run()
        self.assertEqual((result["a_to_b"], result["b_to_c"]),
                         ("verified", "not_authorized"))
        self.assertEqual((self.b.clicks, self.c.clicks, len(self.ops)), (1, 0, 2))

    def test_wrong_b_digest_cannot_authorize_c(self):
        self.b.next_text = self.b_command("substituted body")
        result = self.run()
        self.assertEqual(result["b_to_c"], "not_authorized")
        self.assertEqual(self.c.clicks, 0)

    def test_b_changes_during_c_broker_admission_fails_closed(self):
        def mutate(envelope):
            result = self.broker(envelope)
            if envelope["sender_id"] == B and envelope["op"] == "admit":
                self.b.next_text = self.b_command("changed")
            return result
        original = self.broker
        self.broker = mutate
        # Use a nonrecursive callback to mutate after the first C admission.
        def safe_broker(envelope):
            result = {"admit": {"state": "admitted_not_delivered"},
                      "begin_click": {"state": "click_started_uncertain"}}[envelope["op"]]
            self.ops.append(envelope.copy())
            if envelope["sender_id"] == B and envelope["op"] == "admit":
                self.b.next_text = self.b_command("changed")
            return result
        self.broker = safe_broker
        with self.assertRaises(Exception):
            self.run()
        self.assertEqual(self.c.clicks, 0)
        self.assertEqual(self.ledger.state("m2")[1], "uncertain")
        self.ledger = WakeLedger(self.db)
        before = len(self.ops)
        self.assertEqual(self.run()["b_to_c"], "not_authorized")
        self.assertEqual(self.c.clicks, 0)
        self.assertEqual(len(self.ops), before)

    def test_readonly_preflight_strict_digest_and_legacy_negative(self):
        pa = Page(A, self.a_command())
        browser = Browser([pa, Page(B), Page(C)])
        def check():
            return inspect_boundary(
                browser, a=A, b=B, c=C, source_turn_id="turn-a",
                first_id="m1", payload_sha256=digest(self.first_body),
                pause_checker=lambda: False,
                broker_probe=lambda: {"state": "ready", "outstanding": 0},
                driver_factory=Driver, require_payload_authority=True,
            )
        ok = check()
        self.assertEqual(ok["status"], "preflight_passed_not_delivery")
        self.assertTrue(ok["source_authorizes_exact_payload"])
        pa.text = "BATON_WAKE " + B + " m1"
        bad = check()
        self.assertEqual(bad["status"], "blocked")
        self.assertFalse(bad["source_authorizes_exact_payload"])

    def test_command_shape_rejects_quotes_wrong_hash_and_malformed(self):
        cmd = self.a_command()
        self.assertTrue(source_requested_wake(cmd, B, "m1", digest(self.first_body)))
        self.assertFalse(source_requested_wake("Example: " + cmd, B, "m1",
                                               digest(self.first_body)))
        self.assertFalse(source_requested_wake(cmd, B, "m1", digest("different")))
        self.assertEqual(next_target_from_reply(self.b_command(), C,
                                                digest(self.second_body)), C)
        self.assertIsNone(next_target_from_reply(self.b_command(), C,
                                                  digest("different")))
        with self.assertRaises(ValueError):
            source_requested_wake(cmd, B, "m1", "bad")
        with self.assertRaises(ValueError):
            next_target_from_reply(self.b_command(), C, "BAD")


if __name__ == "__main__":
    unittest.main()
