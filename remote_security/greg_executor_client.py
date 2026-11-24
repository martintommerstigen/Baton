"""Local Baton-to-Greg executor client; connects only to a Unix socket.

A successful socket connection authenticates the *local process UID* to the
executor, not a ChatGPT conversation. Upstream admission must authorize each job.
"""
import json
import socket

def run_local(socket_path, argv, timeout=25):
    if type(socket_path) is not str or not socket_path.startswith("/"):
        raise ValueError("absolute Unix socket path required")
    request = json.dumps({"argv": argv}, ensure_ascii=True, separators=(",",":")).encode()+b"\n"
    if len(request)>16384:
        raise ValueError("request too large")
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        sock.connect(socket_path)
        sock.sendall(request)
        data=bytearray()
        while len(data)<150000:
            chunk=sock.recv(4096)
            if not chunk: break
            data.extend(chunk)
            if data.endswith(b"\n"): break
    if not data.endswith(b"\n") or len(data)>=150000:
        raise RuntimeError("missing or oversized executor receipt; outcome uncertain")
    result=json.loads(data)
    if type(result) is not dict or result.get("state") not in ("completed","timeout_uncertain","rejected"):
        raise RuntimeError("invalid executor receipt")
    return result
