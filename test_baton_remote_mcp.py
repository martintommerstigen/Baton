import http.client
import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from unittest.mock import patch
from baton_remote_mcp import handler_factory


class RemoteMCPTests(unittest.TestCase):
    def setUp(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler_factory("x" * 64))
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def request(self, token, method, params=None, *, body=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method,
                              "params": params or {}}) if body is None else body
        conn.request("POST", "/mcp", payload,
                     {"Authorization": "Bearer " + token, "Content-Type": "application/json"})
        response = conn.getresponse()
        raw = response.read()
        conn.close()
        return response.status, json.loads(raw) if raw else None

    def args(self):
        return {"name": "greg_exec", "arguments": {"argv": ["echo", "hello"],
                                                   "cwd": "/tmp", "timeout": 3}}

    def test_auth_required(self):
        self.assertEqual(self.request("wrong", "tools/list")[0], 401)

    def test_weak_token_rejected(self):
        with self.assertRaises(ValueError):
            handler_factory("short")

    def test_initialize_and_tools_list(self):
        code, data = self.request("x" * 64, "initialize")
        self.assertEqual(code, 200)
        self.assertEqual(data["result"]["serverInfo"]["name"], "baton-greg")
        code, data = self.request("x" * 64, "tools/list")
        self.assertEqual(code, 200)
        self.assertEqual(data["result"]["tools"][0]["name"], "greg_exec")

    def test_closed_ui_fails_closed(self):
        with patch("baton_remote_mcp.ui_lease_active", return_value=False), \
             patch("baton_remote_mcp.execute_on_greg") as core:
            code, data = self.request("x" * 64, "tools/call", self.args())
        self.assertEqual(code, 200)
        self.assertTrue(data["result"]["isError"])
        core.assert_not_called()

    def test_tool_call_routes_to_existing_core(self):
        with patch("baton_remote_mcp.ui_lease_active", return_value=True), \
             patch("baton_remote_mcp.execute_on_greg", return_value={
                 "exit_code": 0, "output": "hello", "truncated": False}) as core:
            code, data = self.request("x" * 64, "tools/call", self.args())
        self.assertEqual(code, 200)
        self.assertFalse(data["result"]["isError"])
        self.assertIn("hello", data["result"]["content"][0]["text"])
        core.assert_called_once_with(["echo", "hello"], "/tmp", 3)

    def test_nonzero_exit_is_error(self):
        with patch("baton_remote_mcp.ui_lease_active", return_value=True), \
             patch("baton_remote_mcp.execute_on_greg", return_value={
                 "exit_code": 9, "output": "failed"}):
            _, data = self.request("x" * 64, "tools/call", self.args())
        self.assertTrue(data["result"]["isError"])

    def test_unreachable_core_fails_closed_without_detail(self):
        with patch("baton_remote_mcp.ui_lease_active", return_value=True), \
             patch("baton_remote_mcp.execute_on_greg", side_effect=RuntimeError("secret path")):
            _, data = self.request("x" * 64, "tools/call", self.args())
        self.assertTrue(data["result"]["isError"])
        self.assertNotIn("secret path", json.dumps(data))

    def test_invalid_arguments_do_not_reach_core(self):
        with patch("baton_remote_mcp.ui_lease_active", return_value=True), \
             patch("baton_remote_mcp.execute_on_greg") as core:
            code, _ = self.request("x" * 64, "tools/call", {"name": "greg_exec", "arguments": {}})
        self.assertEqual(code, 400)
        core.assert_not_called()

    def test_invalid_jsonrpc_rejected(self):
        code, _ = self.request("x" * 64, "tools/list", body='{"id":1,"method":"tools/list"}')
        self.assertEqual(code, 400)


if __name__ == "__main__":
    unittest.main()
