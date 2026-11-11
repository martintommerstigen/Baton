"""Baton local Greg execution endpoint. Explicitly trusted local UID only.

This is a host capability, not a ChatGPT identity proof. Never expose over TCP.
Run as the intended non-root Greg user. The caller must already be authorized
by the Baton admission layer; this broker also checks the kernel peer UID.
"""
import argparse
import json
import os
import socket
import struct
import subprocess

MAX_FRAME = 16384
MAX_OUTPUT = 65536

def execute(request, workdir, timeout=20):
    if type(request) is not dict or set(request) != {"argv"}:
        raise ValueError("invalid request")
    argv = request["argv"]
    if (type(argv) is not list or not 1 <= len(argv) <= 32 or
        any(type(x) is not str or not x or len(x) > 2048 or "\x00" in x for x in argv)):
        raise ValueError("invalid argv")
    # No shell interpolation. Host user permissions apply, including write rights.
    try:
        p = subprocess.run(argv, cwd=workdir, shell=False, stdin=subprocess.DEVNULL,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           timeout=timeout, check=False, close_fds=True)
        return {"state":"completed", "returncode":p.returncode,
                "stdout":p.stdout[:MAX_OUTPUT].decode("utf-8","replace"),
                "stderr":p.stderr[:MAX_OUTPUT].decode("utf-8","replace"),
                "truncated":len(p.stdout)>MAX_OUTPUT or len(p.stderr)>MAX_OUTPUT}
    except subprocess.TimeoutExpired:
        return {"state":"timeout_uncertain", "returncode":None,
                "stdout":"", "stderr":"", "truncated":False}

def serve(path, uid, workdir):
    if os.name != "posix" or not hasattr(socket, "SO_PEERCRED") or os.geteuid() == 0:
        raise RuntimeError("Linux non-root execution required")
    if uid <= 0 or uid == os.geteuid():
        raise ValueError("caller must be a distinct authorized non-root UID")
    if not os.path.isdir(workdir) or not os.path.isabs(workdir):
        raise ValueError("absolute workdir required")
    if os.path.lexists(path):
        raise FileExistsError("refusing to replace socket")
    old = os.umask(0o117)
    s = socket.socket(socket.AF_UNIX)
    try:
        s.bind(path)
    finally:
        os.umask(old)
    os.chmod(path, 0o660)
    s.listen(4)
    try:
        while True:
            conn, _ = s.accept()
            with conn:
                conn.settimeout(3)
                pid, peer_uid, gid = struct.unpack("3i", conn.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
                if peer_uid != uid:
                    continue
                raw = bytearray()
                while len(raw) <= MAX_FRAME and not raw.endswith(b"\n"):
                    chunk = conn.recv(min(4096, MAX_FRAME+1-len(raw)))
                    if not chunk: break
                    raw.extend(chunk)
                try:
                    if not raw.endswith(b"\n") or len(raw)>MAX_FRAME:
                        raise ValueError("invalid frame")
                    req = json.loads(raw.decode("utf-8"))
                    result = execute(req, workdir)
                except (ValueError, UnicodeError, json.JSONDecodeError) as e:
                    result = {"state":"rejected", "error":str(e)}
                conn.sendall((json.dumps(result)+"\n").encode())
    finally:
        s.close()
        # No blind unlink: endpoint ownership/replacement must be checked by operator.

if __name__ == "__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--socket", required=True)
    p.add_argument("--allowed-uid", required=True, type=int)
    p.add_argument("--workdir", required=True)
    a=p.parse_args()
    serve(a.socket,a.allowed_uid,a.workdir)
