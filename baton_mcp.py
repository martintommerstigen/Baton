#!/usr/bin/env python3
"""Baton MCP Streamable HTTP (stateless, loopback-only). Experimental.

This is NOT an internet-facing authentication service. A trusted HTTPS reverse
proxy with ChatGPT-compatible authentication is required before remote use.
"""
import argparse
import hmac
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from baton_local_terminal import execute

VERSION = "2025-03-26"
MAX_BODY = 16384
OPS = ("identity", "system", "git-revision", "python-version")

def rpc(message, workspace):
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
        return 400, {"jsonrpc":"2.0","id":None,"error":{"code":-32600,"message":"Invalid Request"}}
    ident = message.get("id")
    method = message.get("method")
    if method == "notifications/initialized" and ident is None:
        return 202, None
    if ident is None or isinstance(ident, (dict,list,bool)):
        return 400, {"jsonrpc":"2.0","id":None,"error":{"code":-32600,"message":"Invalid Request"}}
    if method == "initialize":
        return 200, {"jsonrpc":"2.0","id":ident,"result":{"protocolVersion":VERSION,"capabilities":{"tools":{"listChanged":False}},"serverInfo":{"name":"baton-greg","version":"0.1.0"}}}
    if method == "ping":
        return 200, {"jsonrpc":"2.0","id":ident,"result":{}}
    if method == "tools/list":
        tools = [{"name":"greg_"+op.replace("-","_"),"description":"Read-only local Greg operation: "+op,"inputSchema":{"type":"object","properties":{},"additionalProperties":False}} for op in OPS]
        return 200, {"jsonrpc":"2.0","id":ident,"result":{"tools":tools}}
    if method == "tools/call":
        params = message.get("params")
        if not isinstance(params,dict) or set(params) != {"name","arguments"} or params["arguments"] != {}:
            return 200, {"jsonrpc":"2.0","id":ident,"error":{"code":-32602,"message":"Invalid params"}}
        name = params["name"]
        if not isinstance(name,str) or not name.startswith("greg_") or name[5:].replace("_","-") not in OPS:
            return 200, {"jsonrpc":"2.0","id":ident,"error":{"code":-32602,"message":"Unknown tool"}}
        try:
            result = execute(name[5:].replace("_","-"),workspace)
        except (OSError,ValueError) as exc:
            result = {"ok":False,"error":type(exc).__name__}
        return 200, {"jsonrpc":"2.0","id":ident,"result":{"content":[{"type":"text","text":json.dumps(result)}],"isError":not result.get("ok",False)}}
    return 200, {"jsonrpc":"2.0","id":ident,"error":{"code":-32601,"message":"Method not found"}}

class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != "/mcp":
            return self.send_json(404, {"error":"not found"})
        auth = self.headers.get("Authorization","")
        token = auth[7:] if auth.startswith("Bearer ") else ""
        if not self.server.token or not hmac.compare_digest(token,self.server.token):
            return self.send_json(401, {"error":"unauthorized"})
        size = self.headers.get("Content-Length","")
        if not size.isdecimal() or int(size)>MAX_BODY:
            return self.send_json(413, {"error":"invalid length"})
        try:
            message = json.loads(self.rfile.read(int(size)))
        except (UnicodeError,ValueError):
            return self.send_json(400, {"error":"invalid JSON"})
        status, result = rpc(message,self.server.workspace)
        self.send_json(status,result)
    def do_GET(self):
        self.send_json(405,{"error":"SSE not supported"})
    def do_DELETE(self):
        self.send_json(405,{"error":"stateless"})
    def send_json(self,status,result):
        payload = b"" if result is None else json.dumps(result).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type","application/json")
        self.send_header("Cache-Control","no-store")
        self.send_header("Content-Length",str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)
    def log_message(self,*_):
        pass

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace",default=str(Path.home()/".local/share/baton-evening"))
    parser.add_argument("--port",type=int,default=8790)
    args = parser.parse_args()
    secret = os.environ.get("BATON_MCP_TOKEN","")
    if len(secret)<32:
        raise SystemExit("Set BATON_MCP_TOKEN to a random 32+ character secret")
    server = ThreadingHTTPServer(("127.0.0.1",args.port),Handler)
    server.token = secret
    server.workspace = args.workspace
    print("Baton MCP listening on 127.0.0.1:"+str(args.port),flush=True)
    server.serve_forever()

if __name__ == "__main__":
    main()
