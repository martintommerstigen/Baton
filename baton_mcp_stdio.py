#!/usr/bin/env python3
"""Baton MCP stdio adapter for an explicitly connected local MCP host.

Run as the Greg desktop user, not root. No GitHub or HTTP server needed.
The host must register this command as an MCP server; merely displaying the
ChatGPT website in a Qt window does NOT register tools in ChatGPT.
"""
import json
import sys
from baton_exec_agent import execute_command

TOOL = {"name":"greg_exec","description":"Execute a program on Greg as the logged-in user, with full user-level filesystem permissions. Do not include secrets in tool arguments or output.","inputSchema":{"type":"object","properties":{"argv":{"type":"array","items":{"type":"string"},"minItems":1,"maxItems":32},"cwd":{"type":"string"},"timeout":{"type":"integer","minimum":1,"maximum":90}},"required":["argv","cwd","timeout"],"additionalProperties":False}}

def handle(message):
    method=message.get("method")
    ident=message.get("id")
    if method=="notifications/initialized":
        return None
    if method=="initialize":
        return {"jsonrpc":"2.0","id":ident,"result":{"protocolVersion":"2025-03-26","capabilities":{"tools":{}},"serverInfo":{"name":"baton-greg","version":"0.1.0"}}}
    if method=="tools/list":
        return {"jsonrpc":"2.0","id":ident,"result":{"tools":[TOOL]}}
    if method=="tools/call":
        params=message.get("params",{})
        if params.get("name")!="greg_exec":
            return {"jsonrpc":"2.0","id":ident,"error":{"code":-32602,"message":"unknown tool"}}
        args=params.get("arguments",{})
        if not isinstance(args,dict) or set(args)!={"argv","cwd","timeout"}:
            return {"jsonrpc":"2.0","id":ident,"error":{"code":-32602,"message":"invalid arguments"}}
        try:
            result=execute_command(args["argv"],args["cwd"],args["timeout"])
            return {"jsonrpc":"2.0","id":ident,"result":{"content":[{"type":"text","text":json.dumps(result)}],"isError":False}}
        except (ValueError,TypeError,OSError,PermissionError) as exc:
            return {"jsonrpc":"2.0","id":ident,"result":{"content":[{"type":"text","text":type(exc).__name__}],"isError":True}}
    return {"jsonrpc":"2.0","id":ident,"error":{"code":-32601,"message":"method not found"}}

def main():
    for line in sys.stdin:
        try:
            message=json.loads(line)
            if not isinstance(message,dict):
                raise ValueError("invalid request")
            response=handle(message)
            if response is not None:
                print(json.dumps(response,separators=(",",":")),flush=True)
        except (ValueError,TypeError,KeyError):
            print(json.dumps({"jsonrpc":"2.0","id":None,"error":{"code":-32700,"message":"invalid JSON-RPC request"}}),flush=True)

if __name__=="__main__":
    main()
