"""B1 H21 negatives: an observer witness is not a ChatGPT assistant turn."""
import hashlib
import types
import unittest
from unittest.mock import patch

from observe_verified_broker_source import (
    ObservationOutcomeUncertain, make_observer_broker_request,
    observe_once, select_existing_source,
)

A = "11111111-1111-4111-8111-111111111111"
B = "22222222-2222-4222-8222-222222222222"
D = hashlib.sha256(b"approved UTF-8 body").hexdigest()
COMMAND = f"BATON_WAKE {B} m-1 sha256:{D}"


class FakeSource:
    def __init__(self, text=COMMAND):
        self.page = types.SimpleNamespace(url=f"https://chatgpt.com/c/{A}")
        self.text = text
        self.calls = 0
        self.generating = False
        self.after_reads = None

    def is_generating(self, source):
        return self.generating

    def read_assistant_turn(self, source, turn):
        self.calls += 1
        if self.after_reads is not None and self.calls >= self.after_reads:
            return "modified"
        return self.text


class ObserverTests(unittest.TestCase):
    def setUp(self):
        self.driver = FakeSource()
        self.sent = []
        self.paused = False

    def broker(self, request):
        self.sent.append(dict(request))
        return {"state": "source_observation_recorded_not_authorship"}

    def run_observer(self, **kwargs):
        return observe_once(
            kwargs.get("driver", self.driver),
            kwargs.get("source", A), kwargs.get("turn", "turn-A"),
            kwargs.get("target", B), kwargs.get("message", "m-1"),
            kwargs.get("digest", D),
            kwargs.get("broker", self.broker),
            kwargs.get("pause", lambda: self.paused),
        )

    def test_positive_is_only_observation_claim(self):
        result = self.run_observer()
        self.assertEqual(result["state"], "source_observation_recorded_not_authorship")
        self.assertIn("not_chatgpt_authorship", result["classification"])
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(self.sent[0]["source_command"], COMMAND)
        self.assertEqual(self.sent[0]["op"], "observe_source")
        self.assertEqual(self.sent[0]["sender_id"], A)
        self.assertGreaterEqual(self.driver.calls, 3)

    def test_wrong_payload_never_calls_broker(self):
        with self.assertRaises(PermissionError):
            self.run_observer(digest="f" * 64)
        self.assertFalse(self.sent)

    def test_quoted_command_never_calls_broker(self):
        self.driver.text = "Example:\\n" + COMMAND
        with self.assertRaises(PermissionError):
            self.run_observer()
        self.assertFalse(self.sent)

    def test_wrong_source_page_never_calls_broker(self):
        self.driver.page.url = f"https://chatgpt.com/c/{B}"
        with self.assertRaises(PermissionError):
            self.run_observer()
        self.assertFalse(self.sent)

    def test_generation_never_calls_broker(self):
        self.driver.generating = True
        with self.assertRaises(RuntimeError):
            self.run_observer()
        self.assertFalse(self.sent)

    def test_pause_never_calls_broker(self):
        self.paused = True
        with self.assertRaises(PermissionError):
            self.run_observer()
        self.assertFalse(self.sent)

    def test_changed_source_before_broker_never_calls(self):
        self.driver.after_reads = 2
        with self.assertRaises(PermissionError):
            self.run_observer()
        self.assertFalse(self.sent)

    def test_changed_source_after_commit_is_uncertain(self):
        self.driver.after_reads = 3
        with self.assertRaises(ObservationOutcomeUncertain):
            self.run_observer()
        self.assertEqual(len(self.sent), 1)

    def test_broker_exception_is_uncertain_not_retry(self):
        def crash(_):
            raise TimeoutError("response lost after possible commit")
        with self.assertRaises(ObservationOutcomeUncertain):
            self.run_observer(broker=crash)
        self.assertEqual(self.driver.calls, 2)

    def test_broker_rejection_is_not_success(self):
        with self.assertRaises(ObservationOutcomeUncertain):
            self.run_observer(broker=lambda _: {"state": "rejected"})
        self.assertEqual(self.driver.calls, 3)

    def test_pause_appears_after_commit_is_uncertain(self):
        count = [0]
        def check():
            count[0] += 1
            return count[0] >= 3
        with self.assertRaises(ObservationOutcomeUncertain):
            self.run_observer(pause=check)
        self.assertEqual(len(self.sent), 1)

    def test_forged_observer_is_known_negative(self):
        # A forged local driver can produce exact text without a real ChatGPT
        # response. This intentionally passes to demonstrate the boundary.
        result = self.run_observer(driver=FakeSource(COMMAND))
        self.assertEqual(result["classification"],
                         "local_observation_claim_not_chatgpt_authorship")

    def test_invalid_identifiers_and_digest(self):
        for kw in ({"source": B}, {"target": "not-uuid"},
                   {"message": "bad space"}, {"digest": "ABC"},
                   {"turn": ""}):
            with self.subTest(kw=kw), self.assertRaises(ValueError):
                self.run_observer(**kw)
        self.assertFalse(self.sent)

    def test_select_exactly_one_preexisting_tab(self):
        page = types.SimpleNamespace(url=f"https://chatgpt.com/c/{A}")
        browser = types.SimpleNamespace(contexts=[
            types.SimpleNamespace(pages=[page])])
        self.assertIs(select_existing_source(browser, A), page)
        browser.contexts[0].pages.append(page)
        with self.assertRaises(RuntimeError):
            select_existing_source(browser, A)
        browser.contexts[0].pages.clear()
        with self.assertRaises(RuntimeError):
            select_existing_source(browser, A)

    def test_broker_client_only_allows_observe_source(self):
        calls = []
        module = types.ModuleType("remote_security.broker_peer")
        def query(path, uid, req, **kwargs):
            calls.append((path, uid, req, kwargs))
            return {"state": "source_observation_recorded_not_authorship"}
        module.query_verified_broker = query
        with patch.dict("sys.modules", {"remote_security": types.ModuleType("remote_security"),
                                        "remote_security.broker_peer": module}):
            with patch("observe_verified_broker_source.os.geteuid", return_value=2002):
                req = make_observer_broker_request("/tmp/baton.sock", 2001)
                self.assertEqual(req({"op": "observe_source"})["state"],
                                 "source_observation_recorded_not_authorship")
                with self.assertRaises(PermissionError):
                    req({"op": "admit"})
                self.assertEqual(len(calls), 1)
                self.assertTrue(calls[0][3]["require_distinct_uid"])


if __name__ == "__main__":
    unittest.main()
