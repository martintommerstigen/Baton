"""Baton Skin-to-Core loopback client. Tokens never enter the web page.

This is the actual boundary between embedded ChatGPT's native Baton Skin
and the already-running Baton local API on Greg. No GitHub command relay.
"""
import json
from pathlib import Path
import urllib.error
import urllib.request

from baton_local_api import load_token

CORE_URL="http://127.0.0.1:52526/v1/exec"

def execute_on_greg(argv, cwd, timeout=30, *, token_file=None):
    token_path=Path(token_file) if token_file else Path.home()/".config/baton/local-api-token"
    token=load_token(token_path)
    body=json.dumps({"argv":argv,"cwd":cwd,"timeout":timeout},
                    separators=(",",":")).encode("utf-8")
    if len(body)>16000:
        raise ValueError("Baton command too long")
    req=urllib.request.Request(
        CORE_URL,body,method="POST",
        headers={"Authorization":"Bearer "+token,"Content-Type":"application/json"})
    try:
        with urllib.request.urlopen(req,timeout=min(timeout+8,100)) as response:
            if response.status!=200:
                raise RuntimeError("Baton Core rejected command")
            raw=response.read(30000)
    except urllib.error.HTTPError as exc:
        raise RuntimeError("Baton Core HTTP "+str(exc.code)) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError("Baton Core is unreachable") from exc
    result=json.loads(raw)
    if not isinstance(result,dict) or "exit_code" not in result or "output" not in result:
        raise RuntimeError("Unexpected Baton Core response")
    return result
