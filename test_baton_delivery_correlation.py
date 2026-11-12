"""Browserless DOM negatives for existing-chat reply correlation.

Runs the generated read-only JS against a tiny fake DOM using Node 22.
No network, browser profile, ChatGPT login or message Send is involved.
"""
import json
from shutil import which
from subprocess import run
import unittest

from baton_chat_observe import inspect_delivery_script, verified_reply_observation


TARGET = "[Baton relay 1234567890abcdef1234567890abcdef · from 11111111-1111-1111-1111-111111111111]\nInspect this question."


def user(text=TARGET):
    return {"role": "user", "text": text}


def assistant(text="An actual distinct answer", turn_id="assistant-new"):
    return {"role": "assistant", "text": text, "id": turn_id}


def observe(turns, streaming=False):
    script = inspect_delivery_script(TARGET)
    js = """
    const rows = %s;
    const streaming = %s;
    const document = {
      querySelectorAll: selector => {
        if (selector !== '[data-message-author-role]') throw Error('unexpected selector');
        return rows.map(row => ({
          innerText: row.text,
          textContent: row.text,
          getAttribute: key => key === 'data-message-author-role'
            ? row.role : key === 'data-message-id' ? (row.id || null) : null
        }));
      },
      querySelector: selector => {
        if (selector !== '[data-testid="stop-button"]') throw Error('unexpected selector');
        return streaming ? {} : null;
      }
    };
    const result = %s;
    process.stdout.write(JSON.stringify(result));
    """ % (json.dumps(turns, ensure_ascii=False), "true" if streaming else "false", script)
    completed = run(["node", "-e", js], capture_output=True, text=True, check=True)
    return json.loads(completed.stdout)


class BatonDeliveryCorrelationTests(unittest.TestCase):
    def test_python_gate_fails_closed(self):
        valid = {
            "userVisible": True, "replyVisible": True, "replyComplete": True,
            "correlation": "unique-adjacent", "assistantMessageId": "id-2"
        }
        self.assertTrue(verified_reply_observation(valid))
        for key, value in (
            ("userVisible", False), ("replyVisible", False),
            ("replyComplete", False), ("correlation", "ambiguous"),
            ("assistantMessageId", None), ("assistantMessageId", " "),
            ("assistantMessageId", "x" * 257)
        ):
            with self.subTest(key=key, value=value):
                self.assertFalse(verified_reply_observation({**valid, key: value}))
        self.assertFalse(verified_reply_observation("wrong-shape"))

    def test_script_rejects_substring_matching(self):
        script = inspect_delivery_script(TARGET)
        self.assertIn("=== needle", script)
        self.assertNotIn(".includes(needle)", script)
        self.assertIn("duplicate-exact-user-turn", script)
        self.assertIn("no-adjacent-assistant-turn", script)

    @unittest.skipUnless(which("node"), "Node needed for browserless JS regression")
    def test_exact_unique_message_and_adjacent_id(self):
        value = observe([assistant("old", "old-id"), user(), assistant()])
        self.assertTrue(verified_reply_observation(value))
        self.assertEqual(value["assistantMessageId"], "assistant-new")
        self.assertEqual(value["reason"], "completed-correlated-turn")

    @unittest.skipUnless(which("node"), "Node needed for browserless JS regression")
    def test_quoted_message_cannot_pretend_delivery(self):
        value = observe([user("A quote: " + TARGET), assistant()])
        self.assertFalse(value["userVisible"])
        self.assertFalse(verified_reply_observation(value))

    @unittest.skipUnless(which("node"), "Node needed for browserless JS regression")
    def test_repeated_exact_user_turn_is_ambiguous(self):
        value = observe([user(), assistant("first", "id1"), user(), assistant("second", "id2")])
        self.assertEqual(value["reason"], "duplicate-exact-user-turn")
        self.assertFalse(verified_reply_observation(value))

    @unittest.skipUnless(which("node"), "Node needed for browserless JS regression")
    def test_later_unrelated_reply_is_not_associated(self):
        value = observe([user(), user("New unrelated user message"), assistant()])
        self.assertEqual(value["reason"], "no-adjacent-assistant-turn")
        self.assertFalse(verified_reply_observation(value))

    @unittest.skipUnless(which("node"), "Node needed for browserless JS regression")
    def test_no_assistant_id_is_not_a_verified_reply(self):
        value = observe([user(), assistant(turn_id=None)])
        self.assertTrue(value["userVisible"])
        self.assertTrue(value["replyVisible"])
        self.assertFalse(value["replyComplete"])
        self.assertEqual(value["reason"], "missing-or-duplicate-assistant-id")
        self.assertFalse(verified_reply_observation(value))

    @unittest.skipUnless(which("node"), "Node needed for browserless JS regression")
    def test_duplicate_assistant_id_is_not_unique_evidence(self):
        value = observe([assistant("old", "assistant-new"), user(), assistant()])
        self.assertFalse(value["replyComplete"])
        self.assertFalse(verified_reply_observation(value))

    @unittest.skipUnless(which("node"), "Node needed for browserless JS regression")
    def test_streaming_is_not_completion(self):
        value = observe([user(), assistant()], streaming=True)
        self.assertEqual(value["reason"], "still-generating")
        self.assertFalse(verified_reply_observation(value))


if __name__ == "__main__":
    unittest.main()
