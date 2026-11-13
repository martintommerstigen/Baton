"""Isolated Baton same-UID capability trial.

Real AF_UNIX connections, an in-memory one-use capability gate and a FAKE
effect sink. Never touches CDP, Qt, ChatGPT, Gemini, portal or production.
A same-UID peer is NOT an authenticated ChatGPT person; an unguessable bearer
token constrains an action but a stolen token remains transferable.
"""
from dataclasses import dataclass
from pathlib import Path
import json
import os
import secrets
import socket
import socketserver
import struct
import threading
import time


@dataclass(frozen=True)
class Grant:
    target: str
    operation: str
    expires: float
    epoch: int


class Gate:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.lock = threading.Lock()
        self._grants = {}
        self._epoch = {}
        self.events = []

    def grant(self, target, operation, ttl=10):
        if operation not in ("observe", "send") or not isinstance(target, str) or not target:
            raise ValueError("unrecognized operation or target")
        if not 0 < ttl <= 30:
            raise ValueError("invalid bounded lifetime")
        with self.lock:
            token = secrets.token_urlsafe(32)
            self._grants[token] = Grant(target, operation, self.clock() + ttl,
                                        self._epoch.get(target, 0))
            return token

    def revoke(self, target):
        with self.lock:
            self._epoch[target] = self._epoch.get(target, 0) + 1

    def effect(self, target, operation, token):
        # A token intentionally never appears in the result or effect log.
        with self.lock:
            grant = self._grants.get(token)
            if (not isinstance(token, str) or not grant or
                grant.target != target or grant.operation != operation or
                grant.expires <= self.clock() or
                grant.epoch != self._epoch.get(target, 0)):
                return {"ok": False, "state": "policy_denied"}
            # Consume once BEFORE fake effect; no replay even if the caller
            # loses the response. Not a real delivery receipt.
            del self._grants[token]
            self.events.append((target, operation, "simulated_effect_only"))
            return {"ok": True, "state": "simulated_effect_only"}


class _Handler(socketserver.StreamRequestHandler):
    def handle(self):
        try:
            raw = self.rfile.readline(4097)
            if len(raw) > 4096:
                reply = {"ok": False, "state": "oversize_denied"}
            else:
                msg = json.loads(raw)
                # Peer UID is only a coarse *OS* check, never author identity.
                uid = struct.unpack("3i", self.request.getsockopt(
                    socket.SOL_SOCKET, socket.SO_PEERCRED, 12))[1]
                if uid != os.getuid():
                    reply = {"ok": False, "state": "peer_uid_denied"}
                elif set(msg) != {"operation", "target", "token"} or not isinstance(
                        msg["operation"], str) or msg["operation"] not in ("observe", "send"):
                    reply = {"ok": False, "state": "operation_denied"}
                else:
                    reply = self.server.gate.effect(msg["target"], msg["operation"],
                                                    msg["token"])
        except (ValueError, TypeError, KeyError, UnicodeError, json.JSONDecodeError):
            reply = {"ok": False, "state": "invalid_request"}
        self.wfile.write((json.dumps(reply) + "\n").encode())


class Server(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, path, gate):
        self.gate = gate
        super().__init__(str(path), _Handler)
        os.chmod(path, 0o600)


def request(path, *, target, operation, token):
    with socket.socket(socket.AF_UNIX) as s:
        s.settimeout(2)
        s.connect(str(path))
        s.sendall((json.dumps({
            "target": target, "operation": operation, "token": token
        }) + "\n").encode())
        buf = b""
        while not buf.endswith(b"\n"):
            next_piece = s.recv(4096)
            if not next_piece:
                break
            buf += next_piece
        return json.loads(buf)
