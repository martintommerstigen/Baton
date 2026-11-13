#!/usr/bin/env python3
"""Baton local-only command bridge.

No GitHub transport. Binds exclusively to loopback, requires a random bearer
token from a mode-0600 local file. Executes as the logged-in user, never root.
A local integration must explicitly attach to this API; embedding a webpage
alone does not grant the hosted model access to localhost.
"""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hmac
import json
import os
from pathlib import Path
import secrets
import stat
from baton_exec_agent import execute_command

MAX_BODY = 16384

def load_token(path):
    path = Path(path)
    if path.is_symlink():
        raise ValueError("token symlink forbidden")
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(secrets.token_hex(32) + "\n")
    mode = path.stat().st_mode
    if not stat.S_ISREG(mode) or mode & 0o077:
        raise ValueError("token permissions must be 0600")
    token = path.read_text().strip()
    if len(token) != 64 or any(c not in "0123456789abcdef" for c in token):
        raise ValueError("invalid token")
    return token

def handler_factory(token):
    class Handler(BaseHTTPRequestHandler):
        def reply(self, status, payload):
            data = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)
        def do_POST(self):
            if self.path != "/v1/exec":
                return self.reply(404, {"error":"not found"})
            auth = self.headers.get("Authorization", "")
            if not hmac.compare_digest(auth, "Bearer " + token):
                return self.reply(401, {"error":"unauthorized"})
            try:
                length = int(self.headers.get("Content-Length","-1"))
                if length < 1 or length > MAX_BODY:
                    return self.reply(413, {"error":"invalid body length"})
                data = json.loads(self.rfile.read(length))
                if not isinstance(data,dict) or set(data) != {"argv","cwd","timeout"}:
                    raise ValueError("invalid shape")
                result = execute_command(data["argv"],data["cwd"],data["timeout"])
                return self.reply(200, result)
            except (ValueError, KeyError, TypeError, OSError, PermissionError) as exc:
                return self.reply(400, {"error":type(exc).__name__})
        def log_message(self, fmt, *args):
            pass
    return Handler

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--port",type=int,default=52526)
    parser.add_argument("--token-file",default=str(Path.home()/".config/baton/local-api-token"))
    args=parser.parse_args()
    if os.geteuid()==0:
        parser.error("run as a normal user, never root")
    if not 1024 <= args.port <= 65535:
        parser.error("invalid port")
    token=load_token(args.token_file)
    server=ThreadingHTTPServer(("127.0.0.1",args.port),handler_factory(token))
    print(f"Baton local API listening on 127.0.0.1:{args.port}",flush=True)
    server.serve_forever()

if __name__=="__main__":
    main()
