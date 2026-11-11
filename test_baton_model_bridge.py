import unittest
from baton_model_protocol import (
    parse_assistant_tool_call,render_tool_call_v2,tool_result_message,observe_assistant_script
)
from baton_model_bridge import bootstrap_message, _json_result_script, _decode_js_result, _assistant_tool_turn, should_auto_arm

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
        one = bootstrap_message(NONCE, "/home/olliver")
        two = bootstrap_message(NONCE, "/home/olliver")
        def first_call(text):
            lines = [line for line in text.splitlines()
                     if line.startswith("BATON_TOOL_V2 ")]
            self.assertEqual(len(lines), 1)
            self.assertEqual(lines[0].count("\\n"), 0)
            return parse_assistant_tool_call(lines[0], NONCE)
        first = first_call(one)
        second = first_call(two)
        self.assertIsNotNone(first)
        self.assertIsNotNone(second)
        self.assertEqual(first["argv"], ["/usr/bin/hostname"])
        self.assertEqual(first["cwd"], "/home/olliver")
        self.assertNotEqual(first["request_id"], second["request_id"])
        self.assertIn("NEXT necessary BATON_TOOL_V2", one)
        self.assertIn("independent read-back", one)
        self.assertIn("not autonomous background thinking", one)

    def test_v2_roundtrip_with_quoted_arguments(self):
        request = self.payload()
        request["argv"] = ["/usr/bin/python3", "-c",
                           "from pathlib import Path; Path('x y').write_text('ok')"]
        request["cwd"] = "/home/olliver/my folder"
        line = render_tool_call_v2(NONCE, request)
        self.assertEqual(line.count("\\n"), 0)
        self.assertEqual(parse_assistant_tool_call(line, NONCE), request)
        self.assertEqual(_assistant_tool_turn({"id":None, "text":line}, NONCE),
                         ("request:" + REQ, request))

    def test_v2_reject_invalid_frames(self):
        request = self.payload()
        line = render_tool_call_v2(NONCE, request)
        self.assertIsNone(parse_assistant_tool_call("Example: " + line, NONCE))
        self.assertIsNone(parse_assistant_tool_call(line + "\\ntext", NONCE))
        self.assertIsNone(parse_assistant_tool_call(line, "d" * 32))
        self.assertIsNone(parse_assistant_tool_call(line.replace(" -- ", " : "), NONCE))
        self.assertIsNone(parse_assistant_tool_call(line.replace(" 15 ", " 91 "), NONCE))
        self.assertIsNone(parse_assistant_tool_call(line + " '", NONCE))

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

    def test_auto_arms_once_per_chat_visit_only(self):
        chat = "6aef828e-0150-83eb-bbac-061f79a8fd4a"
        self.assertTrue(should_auto_arm(chat, None, False, False, False, False))
        self.assertFalse(should_auto_arm(chat, chat, False, False, False, False))
        self.assertFalse(should_auto_arm(chat, None, True, False, False, False))
        self.assertFalse(should_auto_arm(chat, None, False, True, False, False))
        self.assertFalse(should_auto_arm(chat, None, False, False, True, False))
        self.assertFalse(should_auto_arm(chat, None, False, False, False, True))
        self.assertFalse(should_auto_arm(None, None, False, False, False, False))

    def test_spa_navigation_schedules_auto_arm(self):
        # Regression: ChatGPT client-side navigation can change the URL
        # without QtWebEngine emitting a full page loadFinished signal.
        import inspect
        from baton_model_bridge import attach_model_bridge
        source = inspect.getsource(attach_model_bridge)
        navigation = source.split("def on_chat_navigation(url):", 1)[1]
        navigation = navigation.split("def manual_begin():", 1)[0]
        self.assertIn("QTimer.singleShot(1000, auto_arm)", navigation)
        self.assertIn("view.urlChanged.connect(on_chat_navigation)", source)
        self.assertIn("page.loadFinished.connect", source)
        chat = "6aef828e-0150-83eb-bbac-061f79a8fd4a"
        self.assertTrue(should_auto_arm(chat, None, False, False, False, False))
        self.assertFalse(should_auto_arm(chat, chat, False, False, False, False))

    def test_bootstrap_explicit_protocol(self):
        text=bootstrap_message(NONCE,"/home/olliver")
        self.assertIn("BATON_TOOL_V2 "+NONCE,text)
        self.assertIn("/usr/bin/hostname",text)

if __name__=="__main__":
    unittest.main()
