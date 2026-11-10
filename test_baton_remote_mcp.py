import http.client
import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from unittest.mock import patch
from baton_remote_mcp import handler_factory

class RemoteMCPTests(unittest.TestCase):
    def setUp(self):
        self.server=ThreadingHTTPServer(("127.0.0.1",0),handler_factory("x"*64))
        thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
    def request(self,token,method,params=None):
        conn=http.client.HTTPConnection("127.0.0.1",self.server.server_port,timeout=5)
        conn.request("POST","/mcp",json.dumps({"jsonrpc":"2.0","id":1,"method":method,"params":params or {}}),
                     {"Authorization":"Bearer "+token,"Content-Type":"application/json"})
        response=conn.getresponse()
        data=json.loads(response.read())
        conn.close()
        return response.status,data
    def test_auth_required(self):
        self.assertEqual(self.request("wrong","tools/list")[0],401)
    def test_initialize(self):
        code,data=self.request("x"*64,"initialize")
        self.assertEqual(code,200)
        self.assertEqual(data["result"]["serverInfo"]["name"],"baton-greg")
    def test_tools_list(self):
        code,data=self.request("x"*64,"tools/list")
        self.assertEqual(code,200)
        self.assertEqual(data["result"]["tools"][0]["name"],"greg_exec")
    def test_tool_call(self):
        args={"name":"greg_exec","arguments":{"argv":["echo","hello"],"cwd":"/tmp","timeout":3}}
        with patch("baton_remote_mcp.execute_command",return_value={"exit_code":0,"output":"hello","truncated":False}):
            code,data=self.request("x"*64,"tools/call",args)
        self.assertEqual(code,200)
        self.assertIn("hello",data["result"]["content"][0]["text"])
if __name__=="__main__":
    unittest.main()
