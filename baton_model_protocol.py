"""Baton's opt-in text tool protocol for ChatGPT embedded in QtWebEngine.

This is an application protocol over the rendered conversation, not an MCP
registration and not a claim of native ChatGPT tool availability. Never parse
user turns, markdown examples, or assistant prose as executable commands.
"""
import json
import re

NONCE=re.compile(r"^[0-9a-f]{32}$")
CALL=re.compile(r"\ABATON_TOOL_V1 ([0-9a-f]{32})\n(\{[^\n]*\})\nEND_BATON_TOOL_V1\Z",re.S)
REQUEST=re.compile(r"^[0-9a-f]{32}$")

def parse_assistant_tool_call(text, expected_nonce):
    if not isinstance(text,str) or len(text)>7000 or not NONCE.fullmatch(expected_nonce):
        return None
    match=CALL.fullmatch(text.strip())
    if not match or match.group(1)!=expected_nonce:
        return None
    try:
        value=json.loads(match.group(2))
    except ValueError:
        return None
    if not isinstance(value,dict) or set(value)!={"request_id","tool","argv","cwd","timeout"}:
        return None
    if not isinstance(value["request_id"],str) or not REQUEST.fullmatch(value["request_id"]):
        return None
    if value["tool"]!="greg_exec":
        return None
    if not isinstance(value["argv"],list) or not 1<=len(value["argv"])<=32:
        return None
    if any(not isinstance(a,str) or not a or len(a)>4096 or "\x00" in a for a in value["argv"]):
        return None
    if not isinstance(value["cwd"],str) or not value["cwd"].startswith("/") or "\x00" in value["cwd"]:
        return None
    if type(value["timeout"]) is not int or not 1<=value["timeout"]<=90:
        return None
    return value

def tool_result_message(nonce, request_id, result):
    if not NONCE.fullmatch(nonce) or not REQUEST.fullmatch(request_id):
        raise ValueError("invalid tool result IDs")
    if not isinstance(result,dict):
        raise ValueError("invalid tool result")
    bounded={"exit_code":result.get("exit_code"),"timeout":bool(result.get("timeout",False)),
             "truncated":bool(result.get("truncated",False)),
             "output":str(result.get("output",""))[:2400]}
    return ("BATON_TOOL_RESULT_V1 "+nonce+" "+request_id+"\n"+
            json.dumps(bounded,ensure_ascii=False,separators=(",",":"))+
            "\nEND_BATON_TOOL_RESULT_V1")

def observe_assistant_script():
    return """(() => {
      const loading=Boolean(document.querySelector('[data-testid="stop-button"]'));
      if (loading) return [];
      const turns=Array.from(document.querySelectorAll('[data-message-author-role="assistant"]')).slice(-8);
      return turns.map(turn=>({
        id:turn.getAttribute('data-message-id')||null,
        text:(turn.innerText||'').slice(0,7000)
      }));
    })()"""
