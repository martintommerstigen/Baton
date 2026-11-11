"""B1 read-only readiness negatives. No Greg, browser network, or UI sends."""
import hashlib
import unittest

from inspect_b1_readiness import inspect_boundary

A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
C = "cccccccc-cccc-cccc-cccc-cccccccccccc"
DIGEST = hashlib.sha256(b"operator-approved harmless payload").hexdigest()


class Page:
    def __init__(self, cid, text="", generating=False):
        self.url = "https://chatgpt.com/c/" + cid
        self.text = text
        self.generating = generating


class Driver:
    def __init__(self, page, allowed):
        self.page = page
        self.allowed = allowed

    def is_generating(self, cid):
        assert cid in self.allowed
        return self.page.generating

    def read_assistant_turn(self, cid, turn):
        assert cid in self.allowed and turn == "turn-a"
        return self.page.text

    # Intentionally no submit_once, click, fill, or send methods.


class Browser:
    def __init__(self, pages):
        self.contexts = [type("Context", (), {"pages": pages})()]


class ReadinessTests(unittest.TestCase):
    def setUp(self):
        self.a = Page(A, "BATON_WAKE " + B + " m1")
        self.b = Page(B)
        self.c = Page(C)
        self.pages = [self.a, self.b, self.c]
        self.probes = []

    def check(self, *, paused=False, broker=None, **changes):
        if broker is None:
            broker = {"state": "ready", "outstanding": 0}
        opts = dict(
            a=A, b=B, c=C, source_turn_id="turn-a",
            first_id="m1", payload_sha256=DIGEST,
            pause_checker=lambda: paused,
            broker_probe=lambda: self.record_broker(broker),
            driver_factory=Driver,
        )
        opts.update(changes)
        return inspect_boundary(Browser(self.pages), **opts)

    def record_broker(self, value):
        self.probes.append("status_only")
        if isinstance(value, Exception):
            raise value
        return value

    def test_valid_read_only_preflight_is_not_wake_or_payload_authorship(self):
        r = self.check()
        self.assertEqual(r["status"], "preflight_passed_not_delivery")
        self.assertEqual(r["source_command"], "exact_target_and_message_id")
        self.assertFalse(r["source_authorizes_exact_payload"])
        self.assertEqual(r["payload_provenance"], "operator_supplied_not_source_committed")
        self.assertEqual(r["matching_existing_tabs"], {"a": 1, "b": 1, "c": 1})
        self.assertEqual(len(r["source_turn_sha256"]), 64)
        self.assertEqual(self.probes, ["status_only"])

    def test_same_A_command_does_not_commit_payload_digest(self):
        first = self.check()
        second = self.check(payload_sha256=hashlib.sha256(b"different").hexdigest())
        self.assertEqual(first["source_turn_sha256"], second["source_turn_sha256"])
        self.assertEqual(second["status"], "preflight_passed_not_delivery")
        self.assertFalse(second["source_authorizes_exact_payload"])

    def test_pause_active_blocks_even_with_valid_source_and_broker(self):
        r = self.check(paused=True)
        self.assertEqual(r["status"], "blocked")
        self.assertIn("pause_active_or_untrusted", r["reasons"])

    def test_untrusted_pause_result_fails_closed(self):
        r = self.check(pause_checker=lambda: None)
        self.assertIn("pause_active_or_untrusted", r["reasons"])

    def test_broker_outstanding_blocks(self):
        r = self.check(broker={"state": "ready", "outstanding": 1})
        self.assertEqual(r["status"], "blocked")
        self.assertEqual(r["broker_outstanding"], 1)

    def test_broker_exception_fails_closed(self):
        r = self.check(broker=PermissionError("untrusted peer"))
        self.assertEqual(r["status"], "blocked")
        self.assertIn("broker_probe_failed", r["reasons"])

    def test_missing_or_duplicate_tab_blocks(self):
        self.pages = [self.a, self.c]
        self.assertIn("missing_or_duplicate_existing_tab", self.check()["reasons"])
        self.pages = [self.a, self.b, self.c, Page(C)]
        self.assertEqual(self.check()["matching_existing_tabs"]["c"], 2)
        self.assertIn("missing_or_duplicate_existing_tab", self.check()["reasons"])

    def test_source_quote_or_wrong_target_not_authorization(self):
        self.a.text = "Example: BATON_WAKE " + B + " m1"
        self.assertIn("source_command_mismatch", self.check()["reasons"])
        self.a.text = "BATON_WAKE " + C + " m1"
        self.assertIn("source_command_mismatch", self.check()["reasons"])

    def test_streaming_source_or_target_blocks(self):
        self.a.generating = True
        self.assertIn("source_still_generating", self.check()["reasons"])
        self.a.generating = False
        self.c.generating = True
        self.assertIn("c_still_generating", self.check()["reasons"])

    def test_invalid_input_fails_before_any_probe(self):
        with self.assertRaises(ValueError):
            self.check(c=B)
        with self.assertRaises(ValueError):
            self.check(payload_sha256="not-a-digest")
        with self.assertRaises(ValueError):
            self.check(source_turn_id="")
        self.assertEqual(self.probes, [])

    def test_missing_source_turn_does_not_become_authorization(self):
        class MissingTurn(Driver):
            def read_assistant_turn(self, cid, turn):
                raise RuntimeError("missing DOM turn")
        r = self.check(driver_factory=MissingTurn)
        self.assertIn("source_turn_unavailable_or_ambiguous", r["reasons"])
        self.assertEqual(r["status"], "blocked")

    def test_untrusted_broker_shape_never_looks_ready(self):
        for response in ({"state": "admitted_not_delivered"},
                         {"state": "ready", "outstanding": True},
                         {"state": "ready", "outstanding": "0"},
                         {"state": "paused", "outstanding": 0}):
            with self.subTest(response=response):
                self.assertEqual(self.check(broker=response)["status"], "blocked")


if __name__ == "__main__":
    unittest.main()
