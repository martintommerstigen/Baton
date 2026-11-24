"""Loopback remote MCP adapter to the existing authenticated Baton Core.

An authenticated HTTPS reverse proxy is required for remote access. Never expose
this listener directly. Execution requires a live Baton UI lease and uses Core,
not subprocess execution in this adapter.
"""
import hmac
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from baton_core_client import execute_on_greg
from baton_desktop_lease import ui_lease_active
from baton_mcp_stdio import TOOL

MAX_BODY = 16384


def handler_factory(token):
    if not isinstance(token, str) or len(token) < 48:
        raise ValueError("strong remote token required")

    class Handler(BaseHTTPRequestHandler):
        def respond(self, status, obj):
            data = b"" if obj is None else json.dumps(obj).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self):
            if self.path != "/mcp":
                return self.respond(404, {"error": "not found"})
            if not hmac.compare_digest(self.headers.get("Authorization", ""), "Bearer " + token):
                return self.respond(401, {"error": "unauthorized"})
            try:
                length = int(self.headers.get("Content-Length", "-1"))
                if not 1 <= length <= MAX_BODY:
                    return self.respond(413, {"error": "body length"})
                message = json.loads(self.rfile.read(length))
                if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
                    return self.respond(400, {"error": "invalid JSON-RPC"})
                ident, method = message.get("id"), message.get("method")
                if method == "notifications/initialized" and ident is None:
                    return self.respond(202, None)
                if ident is None or isinstance(ident, (dict, list, bool)):
                    return self.respond(400, {"error": "invalid JSON-RPC id"})
                if method == "initialize":
                    result = {"protocolVersion": "2025-03-26", "capabilities": {"tools": {}},
                              "serverInfo": {"name": "baton-greg", "version": "0.2.1"}}
                elif method == "ping":
                    result = {}
                elif method == "tools/list":
                    result = {"tools": [TOOL]}
                elif method == "tools/call":
                    params = message.get("params")
                    if not isinstance(params, dict) or params.get("name") != "greg_exec":
                        return self.respond(400, {"error": "invalid tool"})
                    args = params.get("arguments")
                    if not isinstance(args, dict) or set(args) != {"argv", "cwd", "timeout"}:
                        return self.respond(400, {"error": "invalid arguments"})
                    if not ui_lease_active():
                        result = {"content": [{"type": "text", "text": "Baton UI lease inactive"}],
                                  "isError": True}
                    else:
                        try:
                            outcome = execute_on_greg(args["argv"], args["cwd"], args["timeout"])
                            failed = outcome.get("exit_code") != 0 or bool(outcome.get("timeout", False))
                            result = {"content": [{"type": "text", "text": json.dumps(outcome)}],
                                      "isError": failed}
                        except (ValueError, TypeError, OSError, PermissionError, RuntimeError) as exc:
                            result = {"content": [{"type": "text", "text": type(exc).__name__}],
                                      "isError": True}
                else:
                    return self.respond(400, {"error": "unsupported method"})
                return self.respond(200, {"jsonrpc": "2.0", "id": ident, "result": result})
            except (ValueError, TypeError, UnicodeError):
                return self.respond(400, {"error": "invalid request"})

        def log_message(self, *_):
            pass

    return Handler


def main():
    token = os.environ.get("BATON_REMOTE_TOKEN", "")
    if len(token) < 48:
        raise SystemExit("Set a strong BATON_REMOTE_TOKEN (48+ characters)")
    if os.geteuid() == 0:
        raise SystemExit("Refuse root")
    server = ThreadingHTTPServer(("127.0.0.1", 52527), handler_factory(token))
    server.serve_forever()


if __name__ == "__main__":
    main()
