"""Offline MCP protocol checks; does not require Greg or network."""
import tempfile
import unittest
from baton_mcp import rpc

class MCPTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
    def call(self,method,params=None):
        request={"jsonrpc":"2.0","id":1,"method":method}
        if params is not None:
            request["params"]=params
        return rpc(request,self.tmp.name)
    def test_initialize(self):
        status,reply=self.call("initialize")
        self.assertEqual(status,200)
        self.assertEqual(reply["result"]["protocolVersion"],"2025-03-26")
    def test_list(self):
        _,reply=self.call("tools/list")
        self.assertEqual(len(reply["result"]["tools"]),4)
    def test_allowed(self):
        _,reply=self.call("tools/call",{"name":"greg_identity","arguments":{}})
        self.assertFalse(reply["result"]["isError"])
    def test_unknown_tool(self):
        _,reply=self.call("tools/call",{"name":"greg_shell","arguments":{}})
        self.assertEqual(reply["error"]["code"],-32602)
    def test_extra_arguments(self):
        _,reply=self.call("tools/call",{"name":"greg_identity","arguments":{"command":"sh"}})
        self.assertEqual(reply["error"]["code"],-32602)
    def test_missing_id(self):
        status,reply=rpc({"jsonrpc":"2.0","method":"tools/list"},self.tmp.name)
        self.assertEqual(status,400)
    def test_notification(self):
        status,reply=rpc({"jsonrpc":"2.0","method":"notifications/initialized"},self.tmp.name)
        self.assertEqual((status,reply),(202,None))

if __name__=="__main__":
    unittest.main()
