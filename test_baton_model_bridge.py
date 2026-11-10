import unittest
from baton_model_protocol import (
    parse_assistant_tool_call,tool_result_message,observe_assistant_script
)
from baton_model_bridge import bootstrap_message

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
    def test_bootstrap_explicit_protocol(self):
        text=bootstrap_message(NONCE,"/home/olliver")
        self.assertIn("BATON_TOOL_V1 "+NONCE,text)
        self.assertIn("/usr/bin/hostname",text)

if __name__=="__main__":
    unittest.main()
