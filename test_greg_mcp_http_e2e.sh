#!/usr/bin/env bash
# Verify a full local HTTP MCP exchange on Greg without exposing a port publicly.
set -euo pipefail
cd "${HOME}/.local/share/baton-evening"
secret="$(python3 -c 'import secrets; print(secrets.token_urlsafe(36))')"
port="$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1]); s.close()')"
BATON_MCP_TOKEN="$secret" python3 baton_mcp.py --port "$port" >/dev/null 2>&1 &
pid=$!
cleanup() { kill "$pid" 2>/dev/null || true; wait "$pid" 2>/dev/null || true; }
trap cleanup EXIT
BATON_MCP_TOKEN="$secret" BATON_MCP_PORT="$port" python3 - <<'PY'
import json
import os
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

url = "http://127.0.0.1:" + os.environ["BATON_MCP_PORT"] + "/mcp"
secret = os.environ["BATON_MCP_TOKEN"]
def post(method, params=None, credential=None, notification=False):
    packet = {"jsonrpc":"2.0", "method":method}
    if not notification:
        packet["id"] = 1
    if params is not None:
        packet["params"] = params
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "Authorization": "Bearer " + (secret if credential is None else credential),
    }
    req = Request(url, json.dumps(packet).encode(), headers=headers, method="POST")
    try:
        with urlopen(req, timeout=3) as response:
            raw = response.read()
            return response.status, json.loads(raw) if raw else None
    except HTTPError as err:
        raw = err.read()
        return err.code, json.loads(raw) if raw else None

for attempt in range(40):
    try:
        code, _ = post("initialize", credential="incorrect")
        break
    except URLError:
        time.sleep(0.1)
else:
    raise SystemExit("FAIL: MCP service not ready")
assert code == 401, f"unauthorized response: {code}"
code, initialized = post("initialize", {"protocolVersion":"2025-03-26", "capabilities":{}, "clientInfo":{"name":"greg-test","version":"1.0"}})
assert code == 200 and initialized["result"]["serverInfo"]["name"] == "baton-greg", (code,initialized)
code, _ = post("notifications/initialized", notification=True)
assert code == 202
code, listing = post("tools/list")
names = {tool["name"] for tool in listing["result"]["tools"]}
assert "greg_identity" in names and "greg_shell" not in names, names
code, tool = post("tools/call", {"name":"greg_identity","arguments":{}})
assert code == 200 and not tool["result"]["isError"], (code, tool)
data = json.loads(tool["result"]["content"][0]["text"])
assert data["ok"] and "uid=" in data["output"], data
code, denied = post("tools/call", {"name":"greg_shell","arguments":{}})
assert denied["error"]["code"] == -32602, (code, denied)
print("PASS: MCP unauthorized request denied (401)")
print("PASS: MCP initialize and initialized notification (200/202)")
print("PASS: MCP lists allowlisted tools only")
print("PASS: MCP authenticated greg_identity round-trip")
print("PASS: MCP unknown tool rejected")
print("No public listener or permanent daemon was created.")
PY
