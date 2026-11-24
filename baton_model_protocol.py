"""Baton's opt-in text tool protocol for ChatGPT embedded in QtWebEngine.

This is an application protocol over the rendered conversation, not an MCP
registration and not a claim of native ChatGPT tool availability. Never parse
user turns, markdown examples, or assistant prose as executable commands.
"""
import json
import re
import shlex

NONCE=re.compile(r"^[0-9a-f]{32}$")
CALL=re.compile(r"\ABATON_TOOL_V1 ([0-9a-f]{32})\n(\{[^\n]*\})\nEND_BATON_TOOL_V1\Z",re.S)
REQUEST=re.compile(r"^[0-9a-f]{32}$")
CHAT_ID=re.compile(r"^[0-9a-f]{8}-[0-9a-f-]{20,64}$",re.I)


# The assistant tool line MUST own its whole message. Stripping browser
# accessibility chrome belongs in the observer, never the protocol parser.
# Extracting a line from surrounding prose could execute a quoted example.


def parse_assistant_tool_call(text, expected_nonce):
    if not isinstance(text,str) or len(text)>7000 or not NONCE.fullmatch(expected_nonce):
        return None
    cleaned = text.strip()
    if cleaned.startswith("BATON_CHAT_V1 "):
        if "\n" in cleaned or "\r" in cleaned:
            return None
        try:
            fields = shlex.split(cleaned,posix=True)
        except ValueError:
            return None
        if (len(fields)<6 or fields[0]!="BATON_CHAT_V1"
                or fields[1]!=expected_nonce or fields[4]!="--"):
            return None
        value={"request_id":fields[2],"tool":"chat_send",
               "chat_id":fields[3],"message":" ".join(fields[5:])}
    elif cleaned.startswith("BATON_TOOL_V2 "):
        # A single rendered text line survives hosted ChatGPT markdown/DIL
        # handling that can discard bare multiline JSON in assistant replies.
        # Parse argv only; shlex is NOT a shell and never executes commands.
        if "\n" in cleaned or "\r" in cleaned:
            return None
        try:
            fields = shlex.split(cleaned, posix=True)
        except ValueError:
            return None
        if (len(fields) < 7 or fields[0] != "BATON_TOOL_V2"
                or fields[1] != expected_nonce or fields[5] != "--"
                or not re.fullmatch(r"[0-9]{1,2}", fields[3])):
            return None
        value = {"request_id": fields[2], "tool": "greg_exec",
                 "argv": fields[6:], "cwd": fields[4],
                 "timeout": int(fields[3])}
    else:
        # Legacy V1 is retained for already-issued in-flight requests.
        match = CALL.fullmatch(cleaned)
        if not match or match.group(1) != expected_nonce:
            return None
        try:
            value = json.loads(match.group(2))
        except ValueError:
            return None
    if not isinstance(value,dict):
        return None
    if not isinstance(value.get("request_id"),str) or not REQUEST.fullmatch(value["request_id"]):
        return None
    if value.get("tool")=="chat_send":
        if set(value)!={"request_id","tool","chat_id","message"}:
            return None
        if not isinstance(value["chat_id"],str) or not CHAT_ID.fullmatch(value["chat_id"]):
            return None
        if (not isinstance(value["message"],str) or not value["message"].strip()
                or len(value["message"])>3000 or "\x00" in value["message"]):
            return None
        return value
    if value.get("tool")!="greg_exec" or set(value)!={"request_id","tool","argv","cwd","timeout"}:
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

def render_tool_call_v2(nonce, request):
    """One-line, shell-quoted transport. Never execute through a shell."""
    if not isinstance(request, dict) or set(request) != {
            "request_id", "tool", "argv", "cwd", "timeout"}:
        raise ValueError("invalid request")
    if request.get("tool") != "greg_exec":
        raise ValueError("unsupported tool")
    try:
        frame = " ".join([
            "BATON_TOOL_V2", nonce, request["request_id"],
            str(request["timeout"]), shlex.quote(request["cwd"]), "--",
            *(shlex.quote(arg) for arg in request["argv"])
        ])
    except (TypeError, KeyError) as exc:
        raise ValueError("invalid request") from exc
    if parse_assistant_tool_call(frame, nonce) != request:
        raise ValueError("invalid framed command")
    return frame



def render_chat_call_v1(nonce,request):
    """One strict full-message frame for an exact existing ChatGPT target."""
    if not isinstance(request,dict) or set(request)!={"request_id","tool","chat_id","message"}:
        raise ValueError("invalid request")
    if request.get("tool")!="chat_send":
        raise ValueError("unsupported tool")
    try:
        frame=" ".join([
            "BATON_CHAT_V1",nonce,request["request_id"],request["chat_id"],
            "--",shlex.quote(request["message"])
        ])
    except (TypeError,KeyError) as exc:
        raise ValueError("invalid request") from exc
    if parse_assistant_tool_call(frame,nonce)!=request:
        raise ValueError("invalid framed chat request")
    return frame


def chat_result_message(nonce,request_id,result):
    if not NONCE.fullmatch(nonce) or not REQUEST.fullmatch(request_id):
        raise ValueError("invalid chat result IDs")
    if not isinstance(result,dict):
        raise ValueError("invalid chat result")
    bounded={
        "status":str(result.get("status","unknown"))[:80],
        "target_chat_id":str(result.get("target_chat_id",""))[:80],
        "assistant_message_id":result.get("assistant_message_id"),
        "reply":str(result.get("reply",""))[:2400],
        "detail":str(result.get("detail",""))[:400],
    }
    return ("BATON_CHAT_RESULT_V1 "+nonce+" "+request_id+"\n"+
            json.dumps(bounded,ensure_ascii=False,separators=(",",":"))+
            "\nEND_BATON_CHAT_RESULT_V1")


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
      return turns.map(turn=>{
        const content =
          turn.querySelector('[data-message-content]') ||
          turn.querySelector('.markdown') ||
          turn.querySelector('[class*="markdown"]') ||
          turn;
        return {
          id:turn.getAttribute('data-message-id')||null,
          text:(content.innerText||content.textContent||'').slice(0,7000)
        };
      });
    })()"""
