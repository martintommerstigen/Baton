"""Regression tests for observed existing-chat user-turn provenance.

Synthetic DOM only: does not claim live ChatGPT UI verification.
"""
import unittest

from chatgpt_ui_driver import ChatGPTUIDriver, marker_for, is_marked_user_turn

CHAT = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


class Turn:
    def __init__(self, role, text, turn_id=None):
        self.role = role
        self.text = text
        self.turn_id = turn_id

    def get_attribute(self, name):
        return {"data-message-author-role": self.role,
                "data-message-id": self.turn_id}.get(name)

    def inner_text(self):
        return self.text


class Locator:
    def __init__(self, turns):
        self.turns = turns

    def count(self):
        return len(self.turns)

    def nth(self, index):
        return self.turns[index]


class Page:
    def __init__(self, turns, generating=False):
        self.url = "https://chatgpt.com/c/" + CHAT
        self.turns = turns
        self.generating = generating

    def locator(self, selector):
        if selector == "[data-message-author-role]":
            return Locator(self.turns)
        if selector == '[data-testid="stop-button"]':
            return Locator([object()] if self.generating else [])
        raise AssertionError("unexpected selector: " + selector)


class MarkerObservationTests(unittest.TestCase):
    def setUp(self):
        self.marker = marker_for("wake_123")

    def observe(self, turns, generating=False):
        return ChatGPTUIDriver(Page(turns, generating), frozenset({CHAT})).observe_reply(CHAT, "wake_123")

    def test_exact_first_line_marker_is_required(self):
        self.assertTrue(is_marked_user_turn(self.marker + "\nhello", self.marker))
        self.assertTrue(is_marked_user_turn(self.marker + "\r\nhello", self.marker))
        for text in (
            "Here is a marker " + self.marker + "\nhello",
            "quoted: " + self.marker,
            "hello\n" + self.marker + "\nbody",
            ">" + self.marker + "\nbody",
            self.marker,
            self.marker + "\n \n",
            self.marker + " extra\nbody",
        ):
            with self.subTest(text=text):
                self.assertFalse(is_marked_user_turn(text, self.marker))

    def test_embedded_marker_does_not_verify_unrelated_reply(self):
        turns = [Turn("user", "I quoted " + self.marker + " in a discussion"),
                 Turn("assistant", "unrelated", "unrelated-assistant")]
        self.assertIsNone(self.observe(turns))

    def test_exact_marker_and_next_assistant_turn_verifies(self):
        turns = [Turn("user", self.marker + "\nhello"),
                 Turn("assistant", "reply", "real-assistant")]
        obs = self.observe(turns)
        self.assertEqual((obs.conversation_id, obs.assistant_turn_id),
                         (CHAT, "real-assistant"))

    def test_ambiguous_duplicate_marked_user_turn_fails_closed(self):
        turns = [Turn("user", self.marker + "\nhello"),
                 Turn("assistant", "one", "one"),
                 Turn("user", self.marker + "\nhello"),
                 Turn("assistant", "two", "two")]
        self.assertIsNone(self.observe(turns))

    def test_missing_assistant_turn_id_fails_closed(self):
        self.assertIsNone(self.observe([Turn("user", self.marker + "\nhello"),
                                        Turn("assistant", "reply")]))

    def test_nonadjacent_reply_fails_closed(self):
        self.assertIsNone(self.observe([Turn("user", self.marker + "\nhello"),
                                        Turn("user", "other"),
                                        Turn("assistant", "reply", "id")]))

    def test_generating_response_not_yet_verified(self):
        self.assertIsNone(self.observe([Turn("user", self.marker + "\nhello"),
                                        Turn("assistant", "partial", "id")],
                                       generating=True))


if __name__ == "__main__":
    unittest.main()
