"""B5 client-side identity gate for a dedicated-UID B1 Unix-socket broker.

The peer is checked with Linux SO_PEERCRED *before* any request bytes are sent.
This establishes a kernel UID, not an assistant-turn identity or UI delivery.
No retries, shell, browser actions, network listener, or secret persistence.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import socket
import stat
import struct

MAX_FRAME = 8192


class BrokerUncertain(RuntimeError):
    """Request may have been processed; never resend automatically."""


class UntrustedBroker(PermissionError):
    """Endpoint could not be bound to the configured broker UID."""


def _checked_socket_path(path, expected_uid):
    raw = os.fspath(path)
    if not isinstance(raw, str) or not raw.startswith('/'):
        raise UntrustedBroker('absolute socket path required')
    if any(part in ('', '.', '..') for part in raw.split('/')[1:]):
        raise UntrustedBroker('noncanonical socket path')
    p = Path(raw)
    if p.name in ('', '.', '..'):
        raise UntrustedBroker('socket filename required')
    current = Path('/')
    for component in p.parent.parts[1:]:
        current = current / component
        try:
            info = current.lstat()
        except OSError as exc:
            raise UntrustedBroker('unavailable socket ancestor') from exc
        if not stat.S_ISDIR(info.st_mode):
            raise UntrustedBroker('socket ancestor is not a real directory')
        if info.st_mode & 0o022 and not (info.st_uid == 0 and info.st_mode & stat.S_ISVTX):
            raise UntrustedBroker('writable socket ancestor')
    parent = p.parent.lstat()
    if parent.st_uid not in (0, expected_uid) or parent.st_mode & 0o022:
        raise UntrustedBroker('socket parent not controlled by broker/root')
    try:
        info = p.lstat()
    except OSError as exc:
        raise UntrustedBroker('broker socket unavailable') from exc
    if not stat.S_ISSOCK(info.st_mode) or info.st_uid != expected_uid or info.st_mode & 0o002:
        raise UntrustedBroker('broker socket type/owner/mode rejected')
    return p


def _unique_pairs(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError('duplicate response key')
        out[key] = value
    return out


def query_verified_broker(socket_path, expected_uid, request, *, timeout=3.0,
                          require_distinct_uid=True):
    """One-shot JSON-line exchange, verified peer first, fail closed on ambiguity.

    require_distinct_uid=False is for explicit cooperative-only testing;
    it does NOT protect against a malicious same-UID socket replacement.
    The caller must not treat any broker response as proof of UI delivery.
    """
    if type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 < timeout <= 10:
        raise ValueError('timeout must be finite and within (0,10] seconds')
    if type(expected_uid) is not int or expected_uid < 0:
        raise ValueError('expected_uid must be a nonnegative integer')
    if require_distinct_uid and expected_uid == os.getuid():
        raise UntrustedBroker('same-UID broker is not a security boundary')
    if not hasattr(socket, 'SO_PEERCRED'):
        raise UntrustedBroker('Linux SO_PEERCRED required')
    if type(request) is not dict:
        raise ValueError('request must be a JSON object')
    raw = (json.dumps(request, sort_keys=True, separators=(',', ':'), allow_nan=False)
           + '\n').encode('utf-8')
    if len(raw) > MAX_FRAME:
        raise ValueError('request exceeds frame limit')
    path = _checked_socket_path(socket_path, expected_uid)
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
        conn.settimeout(timeout)
        try:
            conn.connect(str(path))
            credentials = conn.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED,
                                          struct.calcsize('3i'))
            if len(credentials) != struct.calcsize('3i'):
                raise UntrustedBroker('missing kernel peer credentials')
            pid, uid, gid = struct.unpack('3i', credentials)
            if pid <= 0 or uid != expected_uid or gid < 0:
                raise UntrustedBroker('connected broker UID mismatch')
            # Only after verifying the connected peer may bytes leave client.
            conn.sendall(raw)
            conn.shutdown(socket.SHUT_WR)
            response = bytearray()
            while True:
                part = conn.recv(min(4096, MAX_FRAME + 1 - len(response)))
                if not part:
                    break
                response.extend(part)
                if len(response) > MAX_FRAME:
                    raise BrokerUncertain('oversized broker reply')
            if not response.endswith(b'\n') or response.count(b'\n') != 1:
                raise BrokerUncertain('missing or ambiguous broker reply')
            try:
                decoded = json.loads(response[:-1].decode('utf-8'),
                                     object_pairs_hook=_unique_pairs)
            except (ValueError, UnicodeError) as exc:
                raise BrokerUncertain('invalid broker reply') from exc
            if type(decoded) is not dict or type(decoded.get('state')) is not str:
                raise BrokerUncertain('broker reply lacks state')
            return decoded
        except UntrustedBroker:
            raise
        except (OSError, TimeoutError) as exc:
            raise BrokerUncertain('broker outcome uncertain; do not retry') from exc
