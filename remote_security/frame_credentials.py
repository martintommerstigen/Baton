"""B5/B2 Linux AF_UNIX per-frame kernel-credential gate (opt-in).

A socket's SO_PEERCRED describes its original connector, not a later writer
of a delegated descriptor. This reader requires SO_PASSCRED on the listening
socket BEFORE accept and checks SCM_CREDENTIALS on EVERY received segment.
It rejects delegated/forked writers, malformed frames and ambiguous outcomes.

It does not authenticate ChatGPT authorship, authorize UI Send, or retry.
The caller must keep B1's SQLite/PAUSE_UI_WRITES policy and one-use witness.
"""
from __future__ import annotations

import os
import socket
import struct
import time

CRED_SIZE = struct.calcsize("3i")
MAX_FRAME = 8192


class UntrustedFrame(PermissionError):
    """No verified single-process Linux writer for this frame."""


class IncompleteFrame(RuntimeError):
    """A frame was absent, incomplete or timed out; never auto-retry."""


def enable_listener_credentials(listener):
    """Call BEFORE listen/accept; never enable only after data was queued."""
    if (not isinstance(listener, socket.socket) or listener.family != socket.AF_UNIX
            or listener.getsockopt(socket.SOL_SOCKET, socket.SO_TYPE) != socket.SOCK_STREAM
            or not hasattr(socket, "SO_PASSCRED") or not hasattr(socket, "SCM_CREDENTIALS")):
        raise UntrustedFrame("Linux AF_UNIX stream with SCM_CREDENTIALS required")
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_PASSCRED, 1)
    if listener.getsockopt(socket.SOL_SOCKET, socket.SO_PASSCRED) != 1:
        raise UntrustedFrame("SO_PASSCRED could not be enabled")


def _connector(conn):
    if (not isinstance(conn, socket.socket) or conn.family != socket.AF_UNIX
            or conn.getsockopt(socket.SOL_SOCKET, socket.SO_TYPE) != socket.SOCK_STREAM
            or not hasattr(socket, "SO_PASSCRED") or not hasattr(socket, "SCM_CREDENTIALS")):
        raise UntrustedFrame("non-AF_UNIX stream denied")
    if conn.getsockopt(socket.SOL_SOCKET, socket.SO_PASSCRED) != 1:
        raise UntrustedFrame("SO_PASSCRED not inherited from listener")
    raw = conn.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, CRED_SIZE)
    if len(raw) != CRED_SIZE:
        raise UntrustedFrame("missing connector credentials")
    pid, uid, gid = struct.unpack("3i", raw)
    if pid <= 0 or uid <= 0 or gid < 0:
        raise UntrustedFrame("invalid or root connector")
    return pid, uid, gid


def read_authenticated_frame(conn, *, allowed_uids, limit=MAX_FRAME, timeout=3.0):
    """Return (frame_bytes, connector_uid) only if one process wrote all bytes.

    This is an identity gate, NOT an admission or delivery receipt. The caller
    must parse the frame, check its exact schema and apply B1/R22 policy.
    A writer's PID and UID must equal SO_PEERCRED on every recvmsg segment;
    forked or SCM_RIGHTS-delegated descriptors are rejected even if UID matches.
    """
    if (type(limit) is not int or not 0 < limit <= MAX_FRAME
            or type(timeout) not in (float, int) or not 0 < timeout <= 10
            or type(allowed_uids) not in (set, frozenset)
            or not allowed_uids or any(type(u) is not int or u <= 0 for u in allowed_uids)):
        raise ValueError("bounded frame, timeout and non-root UID allowlist required")
    pid, uid, _gid = _connector(conn)
    if uid not in allowed_uids:
        raise UntrustedFrame("connector UID denied")
    deadline = time.monotonic() + timeout
    data = bytearray()
    ancsize = socket.CMSG_SPACE(CRED_SIZE)
    while len(data) <= limit:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise IncompleteFrame("absolute deadline exceeded; no retry")
        conn.settimeout(remaining)
        try:
            chunk, ancillary, flags, _ = conn.recvmsg(min(4096, limit + 1 - len(data)), ancsize)
        except socket.timeout as exc:
            raise IncompleteFrame("frame timed out; no retry") from exc
        if not chunk:
            raise IncompleteFrame("connection closed before complete frame")
        if flags & (socket.MSG_CTRUNC | socket.MSG_TRUNC):
            raise UntrustedFrame("truncated frame or credentials")
        creds = [struct.unpack("3i", raw) for level, typ, raw in ancillary
                 if level == socket.SOL_SOCKET and typ == socket.SCM_CREDENTIALS
                 and len(raw) == CRED_SIZE]
        if len(creds) != 1:
            raise UntrustedFrame("exactly one kernel writer credential required")
        writer_pid, writer_uid, writer_gid = creds[0]
        if writer_pid != pid or writer_uid != uid or writer_gid < 0:
            raise UntrustedFrame("delegated or changed frame writer")
        data.extend(chunk)
        if len(data) > limit:
            raise UntrustedFrame("frame too large")
        if b"\n" in chunk:
            if not data.endswith(b"\n") or data.count(b"\n") != 1:
                raise UntrustedFrame("multiple or trailing frames denied")
            return bytes(data), uid
    raise UntrustedFrame("frame too large")


def _unique_pairs(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError("duplicate JSON field")
        out[key] = value
    return out


class CredentialBoundBrokerHandler(__import__('socketserver').StreamRequestHandler):
    """Opt-in handler for B1's existing Broker, NOT a parallel protocol.

    B1 still owns socket pathname/inode validation, SQLite state, pause and
    click uncertainty. This handler only replaces the unsafe frame read.
    """
    def handle(self):
        import json
        try:
            frame, _uid = read_authenticated_frame(
                self.request, allowed_uids=self.server.allowed_uids)
            if not self.server.endpoint_unchanged():
                return
            req = json.loads(frame.decode('utf-8'), object_pairs_hook=_unique_pairs,
                             parse_constant=lambda _v: (_ for _ in ()).throw(ValueError('nonfinite JSON')))
            if type(req) is not dict:
                return
            result = self.server.store.request_from_socket(self.request, req)
            if not self.server.endpoint_unchanged():
                return
            self.wfile.write((json.dumps(result, sort_keys=True, allow_nan=False)
                              + '\n').encode('utf-8'))
        except (UntrustedFrame, IncompleteFrame, ValueError, UnicodeError,
                OSError, TypeError, RuntimeError):
            # After possible SQLite commit, silence means uncertain; no retry.
            return


def install_credential_bound_handler(broker):
    """Configure an *unstarted* B1-compatible broker, before serving clients.

    Never hot-swap a running broker. B1 owns broker lifecycle and endpoint
    policy. Reject legacy stores with no authenticated socket dispatch.
    """
    import socketserver
    if (not isinstance(broker, socketserver.UnixStreamServer)
            or not callable(getattr(broker, 'endpoint_unchanged', None))
            or not callable(getattr(getattr(broker, 'store', None),
                                    'request_from_socket', None))
            or type(getattr(broker, 'allowed_uids', None)) not in (set, frozenset)
            or not broker.allowed_uids
            or any(type(uid) is not int or uid <= 0 for uid in broker.allowed_uids)):
        raise UntrustedFrame('actual scoped B1 broker and UID policy required')
    enable_listener_credentials(broker.socket)
    broker.RequestHandlerClass = CredentialBoundBrokerHandler
    return broker
