"""Native and legacy ChatGPT DOM reply correlation, no browser/network sends.

The 'native' test DOM reproduces the verified 2026-11-12 QtWebEngine
attributes: data-chatgpt-search-unit-key, data-chatgpt-selection-conversation-id,
data-chatgpt-search-message-ids (including repeated same ID), user bubble,
and assistant markdown text nodes.
"""
import json
from shutil import which
from subprocess import run
import unittest

from baton_chat_observe import inspect_delivery_script, verified_reply_observation

TARGET = "[Baton relay 1234567890abcdef1234567890abcdef · from 11111111-1111-1111-1111-111111111111]\nInspect this question."
CHAT = "6aef828e-0150-83eb-bbac-061f79a8fd4a"


def user(text=TARGET, turn_id="user-new"):
    return {"role": "user", "text": text, "id": turn_id}


def assistant(text="An actual distinct answer", turn_id="assistant-new"):
    return {"role": "assistant", "text": text, "id": turn_id}


def observe(turns, *, native=True, streaming=False, bound=True,
            target=TARGET):
    script = inspect_delivery_script(target)
    javascript = r"""
    const rows = __ROWS__;
    const useNative = __NATIVE__;
    const streaming = __STREAMING__;
    const sourceBound = __BOUND__;
    const chat = '__CHAT__';
    const window = {
      location: {protocol:'https:',hostname:'chatgpt.com',pathname:'/c/'+chat}
    };
    const fakeNative = (row,i) => ({
      getAttribute: key => key === 'data-chatgpt-search-unit-key'
          ? 'fallback-turn-' + i + ':0:' + row.role
          : key === 'data-chatgpt-search-message-ids'
          ? (row.id ? row.id+' '+row.id : '')
          : null,
      querySelector: key => key === '[data-user-message-bubble]'
        ? {innerText:row.text,querySelector: key2 =>
            key2 === '.whitespace-pre-wrap' ? {innerText:row.text} : null}
        : null,
      querySelectorAll: key => key === '[data-markdown-text-style]'
        ? [{innerText:row.text,contains:()=>false}]
        : []
    });
    const fakeLegacy = row => ({
      innerText:row.text,textContent:row.text,
      getAttribute: key => key === 'data-message-author-role'
        ? row.role : key === 'data-message-id' ? (row.id||null) : null
    });
    const document = {
      querySelectorAll: selector => {
        if (selector === '[data-chatgpt-search-unit-key]')
          return useNative ? rows.map(fakeNative) : [];
        if (selector === '[data-message-author-role]')
          return useNative ? [] : rows.map(fakeLegacy);
        if (selector === '[data-chatgpt-selection-conversation-id]')
          return useNative ? [{getAttribute:()=> sourceBound ? chat
                                          : '00000000-0000-0000-0000-000000000000'}] : [];
        if (selector === 'button')
          return streaming ? [{getAttribute:()=> 'Stop'}] : [];
        throw Error('unexpected selector: '+selector);
      },
      querySelector: selector => {
        if (selector === '[data-testid="stop-button"]') return streaming ? {} : null;
        throw Error('unexpected querySelector: '+selector);
      }
    };
    const output = __SCRIPT__;
    process.stdout.write(JSON.stringify(output));
    """
    for k,v in (("__ROWS__",json.dumps(turns,ensure_ascii=True)),
                ("__NATIVE__",str(native).lower()),
                ("__STREAMING__",str(streaming).lower()),
                ("__BOUND__",str(bound).lower()),
                ("__CHAT__",CHAT),
                ("__SCRIPT__",script)):
        javascript=javascript.replace(k,v)
    completed=run(["node","-e",javascript],
                  capture_output=True,text=True,check=True)
    return json.loads(completed.stdout)


class BatonDeliveryCorrelationTests(unittest.TestCase):
    def test_python_gate_fails_closed(self):
        valid = {"userVisible":True,"replyVisible":True,"replyComplete":True,
                 "correlation":"unique-adjacent","assistantMessageId":"id-2"}
        self.assertTrue(verified_reply_observation(valid))
        for key,value in (
            ("userVisible",False),("replyVisible",False),
            ("replyComplete",False),("correlation","ambiguous"),
            ("assistantMessageId",None),("assistantMessageId"," "),
            ("assistantMessageId","x"*257)
        ):
            with self.subTest(key=key,value=value):
                self.assertFalse(verified_reply_observation({**valid,key:value}))
        self.assertFalse(verified_reply_observation("wrong-shape"))

    def test_no_substring_authentication(self):
        js=inspect_delivery_script(TARGET)
        self.assertIn("=== needle",js)
        self.assertNotIn(".includes(needle)",js)
        self.assertIn("duplicate-exact-user-turn",js)
        self.assertIn("source-conversation-not-bound",js)

    @unittest.skipUnless(which("node"),"Node is required")
    def test_native_actual_attribute_shape_verified(self):
        value=observe([user(),assistant()],native=True)
        self.assertTrue(verified_reply_observation(value))
        self.assertEqual(value["schema"],"native")
        self.assertEqual(value["assistantMessageId"],"assistant-new")

    @unittest.skipUnless(which("node"),"Node is required")
    def test_legacy_still_works(self):
        value=observe([assistant("older","old-id"),user(),assistant()],
                      native=False)
        self.assertTrue(verified_reply_observation(value))
        self.assertEqual(value["schema"],"legacy")

    @unittest.skipUnless(which("node"),"Node is required")
    def test_native_rejects_wrong_source_marker(self):
        value=observe([user(),assistant()],bound=False)
        self.assertEqual(value["reason"],"source-conversation-not-bound")
        self.assertFalse(verified_reply_observation(value))

    @unittest.skipUnless(which("node"),"Node is required")
    def test_quote_is_not_a_user_turn(self):
        value=observe([user("Only quoting: "+TARGET),assistant()])
        self.assertFalse(value["userVisible"])
        self.assertFalse(verified_reply_observation(value))

    @unittest.skipUnless(which("node"),"Node is required")
    def test_native_duplicate_exact_payload_is_ambiguous(self):
        value=observe([user(),assistant("one","id-1"),user("Different content","id-2"),
                       user(turn_id="second-target-user"),assistant("two","id-3")])
        self.assertEqual(value["reason"],"duplicate-exact-user-turn")
        self.assertFalse(verified_reply_observation(value))

    @unittest.skipUnless(which("node"),"Node is required")
    def test_image_only_user_turn_is_still_a_reply_boundary(self):
        # A user can send an attachment without extracted text. Its reply
        # must not be attributed to an earlier Baton request.
        value=observe([user(),user("", "image-only-user"),
                       assistant("Reply to the image", "image-answer")])
        self.assertFalse(verified_reply_observation(value))
        self.assertEqual(value["reason"],"no-adjacent-assistant-turn")
        self.assertIsNone(value["assistantMessageId"])

    @unittest.skipUnless(which("node"),"Node is required")
    def test_empty_assistant_turn_cannot_be_skipped(self):
        # A rendered assistant turn with no extracted markdown is still a
        # boundary; a later assistant message is not the expected reply.
        value=observe([user(),assistant("", "empty-assistant"),
                       assistant("Later unrelated answer", "later-answer")])
        self.assertFalse(verified_reply_observation(value))
        self.assertEqual(value["reason"],"empty-reply")
        self.assertFalse(value["replyComplete"])

    @unittest.skipUnless(which("node"),"Node is required")
    def test_later_unrelated_reply_is_not_a_receipt(self):
        value=observe([user(),user("Unrelated request","unrelated-user-id"),assistant()])
        self.assertEqual(value["reason"],"no-adjacent-assistant-turn")
        self.assertFalse(verified_reply_observation(value))

    @unittest.skipUnless(which("node"),"Node is required")
    def test_no_assistant_id_is_not_a_receipt(self):
        value=observe([user(),assistant(turn_id=None)])
        self.assertFalse(verified_reply_observation(value))
        self.assertEqual(value["reason"],"missing-or-duplicate-assistant-id")

    @unittest.skipUnless(which("node"),"Node is required")
    def test_duplicate_assistant_id_must_not_correlate(self):
        value=observe([assistant("different","assistant-new"),user(),assistant()])
        self.assertFalse(verified_reply_observation(value))

    @unittest.skipUnless(which("node"),"Node is required")
    def test_streaming_is_not_complete(self):
        value=observe([user(),assistant()],streaming=True)
        self.assertEqual(value["reason"],"still-generating")
        self.assertFalse(verified_reply_observation(value))

    @unittest.skipUnless(which("node"),"Node is required")
    def test_legacy_missing_id_fails_closed(self):
        value=observe([user(),assistant(turn_id=None)],native=False)
        self.assertFalse(verified_reply_observation(value))

    @unittest.skipUnless(which("node"),"Node is required")
    def test_native_assistant_text_restricted_to_markdown(self):
        value=observe([user(),assistant(text="Short honest answer")])
        self.assertTrue(verified_reply_observation(value))
        self.assertEqual(value["assistantText"],"Short honest answer")


if __name__ == "__main__":
    unittest.main()
