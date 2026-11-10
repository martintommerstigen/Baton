"""Small remote MCP HTTP adapter for Baton Core.

Run only behind a trusted HTTPS reverse proxy with authentication and an
explicitly configured BATON_REMOTE_TOKEN. Do not publish the local execution
API itself. Remote clients must supply Bearer token on every request.
"""
import hmac
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from baton_exec_agent import execute_command
from baton_mcp_stdio import TOOL

def handler_factory(token):
    class Handler(BaseHTTPRequestHandler):
        def respond(self, status, obj):
            data=json.dumps(obj).encode()
            self.send_response(status)
            self.send_header("Content-Type","application/json")
            self.send_header("Content-Length",str(len(data)))
            self.send_header("Cache-Control","no-store")
            self.end_headers()
            self.wfile.write(data)
        def do_POST(self):
            if self.path!="/mcp":
                return self.respond(404,{"error":"not found"})
            if not hmac.compare_digest(self.headers.get("Authorization",""),"Bearer "+token):
                return self.respond(401,{"error":"unauthorized"})
            try:
                length=int(self.headers.get("Content-Length","-1"))
                if not 1<=length<=16384:
                    return self.respond(413,{"error":"body length"})
                message=json.loads(self.rfile.read(length))
                ident=message.get("id")
                method=message.get("method")
                if method=="initialize":
                    result={"protocolVersion":"2025-03-26","capabilities":{"tools":{}},"serverInfo":{"name":"baton-greg","version":"0.1.0"}}
                elif method=="tools/list":
                    result={"tools":[TOOL]}
                elif method=="tools/call":
                    params=message.get("params",{})
                    if params.get("name")!="greg_exec":
                        raise ValueError("unknown tool")
                    args=params.get("arguments",{})
                    if not isinstance(args,dict) or set(args)!={"argv","cwd","timeout"}:
                        raise ValueError("invalid arguments")
                    outcome=execute_command(args["argv"],args["cwd"],args["timeout"])
                    result={"content":[{"type":"text","text":json.dumps(outcome)}],"isError":False}
                else:
                    return self.respond(400,{"error":"unsupported method"})
                return self.respond(200,{"jsonrpc":"2.0","id":ident,"result":result})
            except (ValueError,KeyError,TypeError,OSError,PermissionError):
                return self.respond(400,{"error":"invalid request"})
        def log_message(self,*args):
            pass
    return Handler

def main():
    token=os.environ.get("BATON_REMOTE_TOKEN","")
    if len(token)<48:
        raise SystemExit("Set a strong BATON_REMOTE_TOKEN (48+ characters)")
    if os.geteuid()==0:
        raise SystemExit("Refuse root")
    # Loopback only. HTTPS reverse proxy must be independently configured.
    server=ThreadingHTTPServer(("127.0.0.1",52527),handler_factory(token))
    server.serve_forever()

if __name__=="__main__":
    main()
