#!/usr/bin/env bash
# Run on Greg only. Local end-to-end verification; no external listener.
set -euo pipefail
cd "${HOME}/.local/share/baton-evening"
python3 -m unittest -v test_baton_local_terminal.py test_preflight_greg.py test_baton_loopback_http.py
secret="$(python3 -c 'import secrets; print(secrets.token_urlsafe(36))')"
port="$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1]); s.close()')"
BATON_LOCAL_TOKEN="$secret" python3 baton_loopback_http.py --port "$port" > /dev/null 2>&1 &
pid=$!
cleanup() { kill "$pid" 2>/dev/null || true; wait "$pid" 2>/dev/null || true; }
trap cleanup EXIT
BATON_LOCAL_TOKEN="$secret" BATON_LOCAL_PORT="$port" python3 - <<'PY'
import json
import os
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

base = "http://127.0.0.1:" + os.environ["BATON_LOCAL_PORT"] + "/v1/execute"
token = os.environ["BATON_LOCAL_TOKEN"]

def request(operation, credential):
    data = json.dumps({"operation": operation}).encode()
    req = Request(base, data=data, headers={"Authorization": "Bearer " + credential, "Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=2) as response:
            return response.status, json.load(response)
    except HTTPError as error:
        return error.code, json.load(error)

for _ in range(30):
    try:
        status, result = request("identity", "wrong-token")
        break
    except URLError:
        time.sleep(.1)
else:
    raise SystemExit("FAIL: local HTTP service did not start")
assert status == 401, (status, result)
status, result = request("identity", token)
assert status == 200 and result.get("ok") and "uid=" in result.get("output", ""), (status, result)
status, result = request("arbitrary-shell", token)
assert status == 400, (status, result)
print("PASS: unauthorized request denied (401)")
print("PASS: authenticated identity executed on local adapter (200)")
print("PASS: arbitrary operation denied (400)")
print("NOTE: this does not connect ChatGPT to Greg.")
PY
