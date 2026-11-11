import json
import subprocess
import sys
import unittest
from unittest.mock import patch
from baton_mcp_stdio import handle

class MCPTests(unittest.TestCase):
    def test_initialize(self):
        r=handle({"jsonrpc":"2.0","id":1,"method":"initialize","params":{}})
        self.assertEqual(r["result"]["serverInfo"]["name"],"baton-greg")
    def test_tools_list(self):
        r=handle({"jsonrpc":"2.0","id":2,"method":"tools/list"})
        self.assertEqual(r["result"]["tools"][0]["name"],"greg_exec")
    def test_exec(self):
        with patch("baton_mcp_stdio.execute_on_greg",return_value={"exit_code":0,"output":"hello","truncated":False}):
            r=handle({"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"greg_exec","arguments":{"argv":["echo","hello"],"cwd":"/tmp","timeout":5}}})
        self.assertIn("hello",r["result"]["content"][0]["text"])
    def test_core_unreachable_fails_closed(self):
        with patch("baton_mcp_stdio.execute_on_greg",
                   side_effect=RuntimeError("Baton Core is unreachable")):
            r=handle({"jsonrpc":"2.0","id":7,"method":"tools/call",
                      "params":{"name":"greg_exec","arguments":{
                          "argv":["/usr/bin/true"],"cwd":"/tmp","timeout":5}}})
        self.assertTrue(r["result"]["isError"])
        self.assertIn("RuntimeError",r["result"]["content"][0]["text"])
        self.assertNotIn("Baton Core is unreachable",r["result"]["content"][0]["text"])

    def test_command_nonzero_is_mcp_error(self):
        with patch("baton_mcp_stdio.execute_on_greg",
                   return_value={"exit_code":2,"output":"failed","timeout":False}):
            r=handle({"jsonrpc":"2.0","id":8,"method":"tools/call",
                      "params":{"name":"greg_exec","arguments":{
                          "argv":["/usr/bin/false"],"cwd":"/tmp","timeout":5}}})
        self.assertTrue(r["result"]["isError"])
        self.assertIn("failed",r["result"]["content"][0]["text"])

    def test_missing_argument(self):
        r=handle({"jsonrpc":"2.0","id":4,"method":"tools/call","params":{"name":"greg_exec","arguments":{}}})
        self.assertEqual(r["error"]["code"],-32602)
    def test_unknown_tool(self):
        r=handle({"jsonrpc":"2.0","id":5,"method":"tools/call","params":{"name":"other","arguments":{}}})
        self.assertEqual(r["error"]["code"],-32602)
    def test_stdio_protocol(self):
        data='{"jsonrpc":"2.0","id":1,"method":"tools/list"}\n'
        proc=subprocess.run([sys.executable,"baton_mcp_stdio.py"],input=data,text=True,capture_output=True,timeout=5)
        self.assertEqual(proc.returncode,0)
        self.assertEqual(json.loads(proc.stdout)["result"]["tools"][0]["name"],"greg_exec")
if __name__=="__main__":
    unittest.main()
