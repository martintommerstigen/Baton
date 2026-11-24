#!/usr/bin/env python3
"""Loopback-only read-only Baton HTTP adapter; no arbitrary shell."""
import hmac
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from baton_local_terminal import execute

OPERATIONS = frozenset(("identity", "system", "git-revision", "python-version"))
MAX_BODY = 2048

def dispatch(path, body, token, expected, workspace):
    if not expected or not hmac.compare_digest(token, expected):
        return 401, {"error": "unauthorized"}
    if path != "/v1/execute":
        return 404, {"error": "not found"}
    if not isinstance(body, dict) or set(body) != {"operation"}:
        return 400, {"error": "invalid request"}
    operation = body["operation"]
    if not isinstance(operation, str) or operation not in OPERATIONS:
        return 400, {"error": "operation not allowed"}
    try:
        return 200, execute(operation, workspace)
    except (ValueError, OSError) as exc:
        return 400, {"error": type(exc).__name__}

class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != "/v1/execute":
            return self.reply(404, {"error": "not found"})
        header = self.headers.get("Authorization", "")
        token = header[7:] if header.startswith("Bearer ") else ""
        if not self.server.token or not hmac.compare_digest(token, self.server.token):
            return self.reply(401, {"error": "unauthorized"})
        length = self.headers.get("Content-Length", "")
        if not length.isdecimal() or int(length) > MAX_BODY:
            return self.reply(413, {"error": "invalid length"})
        try:
            payload = json.loads(self.rfile.read(int(length)))
        except (ValueError, UnicodeDecodeError):
            return self.reply(400, {"error": "invalid JSON"})
        status, result = dispatch(self.path, payload, token, self.server.token, self.server.workspace)
        self.reply(status, result)
    def do_GET(self):
        self.reply(404, {"error": "not found"})
    def reply(self, status, payload):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def log_message(self, *_):
        pass

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", default=str(Path.home() / ".local/share/baton-evening"))
    parser.add_argument("--port", type=int, default=8789)
    args = parser.parse_args()
    token = os.environ.get("BATON_LOCAL_TOKEN", "")
    if len(token) < 32:
        raise SystemExit("BATON_LOCAL_TOKEN must be a random 32+ character secret")
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    server.token = token
    server.workspace = args.workspace
    print(f"Baton local HTTP ready on 127.0.0.1:{args.port}", flush=True)
    server.serve_forever()

if __name__ == "__main__":
    main()
