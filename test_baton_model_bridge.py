import unittest
from baton_model_protocol import (
    parse_assistant_tool_call,tool_result_message,observe_assistant_script
)
from baton_model_bridge import bootstrap_message, _json_result_script, _decode_js_result, _assistant_tool_turn

NONCE="b"*32
REQ="c"*32

def frame(payload, nonce=NONCE):
    import json
    return "BATON_TOOL_V1 "+nonce+"\n"+json.dumps(payload,separators=(",",":"))+"\nEND_BATON_TOOL_V1"

class ModelToolTests(unittest.TestCase):
    def payload(self):
        return {"request_id":REQ,"tool":"greg_exec","argv":["/usr/bin/hostname"],
                "cwd":"/home/olliver","timeout":15}
    def test_valid_request(self):
        self.assertEqual(parse_assistant_tool_call(frame(self.payload()),NONCE),self.payload())
    def test_nonce_mismatch(self):
        self.assertIsNone(parse_assistant_tool_call(frame(self.payload()),"d"*32))
    def test_prose_and_fenced_quote_not_commands(self):
        command=frame(self.payload())
        self.assertIsNone(parse_assistant_tool_call("Example:\n"+command,NONCE))
        self.assertIsNone(parse_assistant_tool_call("```json\n"+command+"\n```",NONCE))
    def test_invalid_shape(self):
        p=self.payload()
        p["secret"]="unsafe"
        self.assertIsNone(parse_assistant_tool_call(frame(p),NONCE))
    def test_reject_shell_string(self):
        p=self.payload()
        p["argv"]="bash -c echo"
        self.assertIsNone(parse_assistant_tool_call(frame(p),NONCE))
    def test_bounded_tool_result(self):
        message=tool_result_message(NONCE,REQ,{"exit_code":0,"output":"a"*6000})
        self.assertLess(len(message),2700)
        self.assertIn("BATON_TOOL_RESULT_V1",message)
    def test_observer_restricts_assistant(self):
        script=observe_assistant_script()
        self.assertIn('data-message-author-role="assistant"',script)
    def test_qt_json_result_bridge(self):
        self.assertEqual(_decode_js_result('{"ok":true,"reason":"prepared"}'),
                         {"ok": True, "reason": "prepared"})
        self.assertEqual(_decode_js_result('{"ok":false,"reason":"composer-not-found"}'),
                         {"ok": False, "reason": "composer-not-found"})
        self.assertEqual(_decode_js_result(None), None)
        self.assertEqual(_decode_js_result('not-json')["reason"], "invalid-json-result")
        script = _json_result_script("(() => ({ok:true}))()")
        self.assertIn("JSON.stringify", script)
        self.assertIn("js-exception:", script)

    def test_bootstrap_prompts_real_work_and_fresh_first_call(self):
        import re
        import json
        one = bootstrap_message(NONCE, "/home/olliver")
        two = bootstrap_message(NONCE, "/home/olliver")
        pattern = r"(?m)^BATON_TOOL_V1 ([0-9a-f]{32})\n(\{[^\n]+\})\nEND_BATON_TOOL_V1$"
        match_one = re.search(pattern, one)
        match_two = re.search(pattern, two)
        self.assertIsNotNone(match_one)
        self.assertIsNotNone(match_two)
        self.assertEqual(match_one.group(1), NONCE)
        first = json.loads(match_one.group(2))
        second = json.loads(match_two.group(2))
        self.assertEqual(first["argv"], ["/usr/bin/hostname"])
        self.assertEqual(first["cwd"], "/home/olliver")
        self.assertNotEqual(first["request_id"], second["request_id"])
        self.assertIn("NEXT necessary BATON_TOOL_V1", one)
        self.assertIn("read-back verification", one)
        self.assertIn("NOT perpetual background execution", one)

    def test_tool_turn_without_dom_message_id(self):
        valid = frame(self.payload())
        turn_id, parsed = _assistant_tool_turn({"id":None,"text":valid}, NONCE)
        self.assertEqual(turn_id, "request:"+REQ)
        self.assertEqual(parsed, self.payload())
        self.assertEqual(_assistant_tool_turn({"id":"turn42","text":valid},NONCE)[0], "turn42")
        self.assertIsNone(_assistant_tool_turn({"id":None,"text":valid},"d"*32))
        self.assertIsNone(_assistant_tool_turn({"id":None,"text":"Example:\n"+valid},NONCE))
        self.assertIsNone(_assistant_tool_turn({"id":None,"text":frame(self.payload(), "d"*32)},NONCE))
        self.assertIsNone(_assistant_tool_turn({"id":None,"text":""},NONCE))

    def test_bootstrap_explicit_protocol(self):
        text=bootstrap_message(NONCE,"/home/olliver")
        self.assertIn("BATON_TOOL_V1 "+NONCE,text)
        self.assertIn("/usr/bin/hostname",text)

if __name__=="__main__":
    unittest.main()
