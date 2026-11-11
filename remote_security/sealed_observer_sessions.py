"""B5/R27: four preconnected, role-pinned B1 H24 one-shot Unix sessions.

B1's source protocol needs snapshot, snapshot, witness, snapshot (not one
persistent channel). This is an offline integration adapter, NOT an existing
ChatGPT conversation wake, source authorship attestation, or UI permission.
Requires pinned R25/R26, R24 preflight before connection and R23 on servers.
Never retry a possibly processed witness. Do not deploy on Greg yet.
"""
from __future__ import annotations

import errno
import json
import os
import re
import socket
import struct
import sys
import threading
import time

from remote_security.sealed_unix_channel import (
    ChannelSealDenied, _check_path, _load_filter, _r25_kernel_prerequisite,
)


def _required(check, *args):
    try:
        return check(*args)
    except ChannelSealDenied as exc:
        raise SessionSealDenied(str(exc)) from exc


class SessionSealDenied(PermissionError):
    pass


class SessionUncertain(RuntimeError):
    """The broker may have committed; never resend."""


def _socket_inventory():
    try:
        result = {}
        for name in os.listdir("/proc/self/fd"):
            if name.isdecimal():
                try:
                    target = os.readlink("/proc/self/fd/" + name)
                except FileNotFoundError:
                    continue
                if target.startswith("socket:"):
                    result[int(name)] = target
        return result
    except OSError as exc:
        raise SessionSealDenied("socket descriptor audit unavailable") from exc


def seal_observer_sessions(snapshots, witness, *, snapshot_endpoint,
                           witness_endpoint, collector_uid, broker_uid,
                           approved_snapshot, pause_checker):
    """Seal three collector streams and one separate witness stream.

    Call only from a dedicated single-threaded non-root observer, after R25
    and a successful R24 preflight, before sending any source/witness request.
    The caller must close all streams and terminate the worker on failure.
    """
    keys = {"op", "source_id", "origin_turn_id", "target_id",
            "message_id", "payload_sha256"}
    if (type(approved_snapshot) is not dict or set(approved_snapshot) != keys
            or approved_snapshot.get("op") != "snapshot"
            or any(type(v) is not str for v in approved_snapshot.values())
            or not callable(pause_checker) or pause_checker() is not False):
        raise SessionSealDenied("exact approved request and inactive pause required")
    chat = r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}"
    if (not re.fullmatch(chat, approved_snapshot["source_id"])
            or not re.fullmatch(chat, approved_snapshot["target_id"])
            or approved_snapshot["source_id"] == approved_snapshot["target_id"]
            or not re.fullmatch(r"[0-9a-f]{64}", approved_snapshot["payload_sha256"])
            or not 1 <= len(approved_snapshot["origin_turn_id"]) <= 128
            or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", approved_snapshot["message_id"])):
        raise SessionSealDenied("invalid fixed source/target/message/digest")
    if (not sys.platform.startswith("linux") or os.getuid() != os.geteuid()
            or os.geteuid() == 0 or threading.active_count() != 1):
        raise SessionSealDenied("single-threaded non-root Linux observer required")
    if (type(collector_uid) is not int or type(broker_uid) is not int
            or min(collector_uid, broker_uid) <= 0
            or len({os.geteuid(), collector_uid, broker_uid}) != 3):
        raise SessionSealDenied("three distinct non-root UID roles required")
    if type(snapshots) not in (tuple, list) or len(snapshots) != 3:
        raise SessionSealDenied("three snapshot streams required")
    streams = tuple(snapshots) + (witness,)
    if (any(not isinstance(s, socket.socket) or s.fileno() < 0 for s in streams)
            or len({s.fileno() for s in streams}) != 4
            or snapshot_endpoint == witness_endpoint):
        raise SessionSealDenied("four separate role-pinned descriptors required")
    before = (_required(_check_path, snapshot_endpoint, collector_uid),
              _required(_check_path, witness_endpoint, broker_uid))
    for sock, endpoint, uid in zip(
            streams, (snapshot_endpoint,) * 3 + (witness_endpoint,),
            (collector_uid,) * 3 + (broker_uid,)):
        try:
            if (sock.family != socket.AF_UNIX or sock.type & 0xf != socket.SOCK_STREAM
                    or sock.getpeername() != endpoint):
                raise SessionSealDenied("socket family, type or path mismatch")
            pid, actual_uid, gid = struct.unpack(
                "3i", sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED,
                                     struct.calcsize("3i")))
        except (OSError, struct.error) as exc:
            raise SessionSealDenied("kernel peer identity unavailable") from exc
        if pid <= 0 or actual_uid != uid or gid < 0:
            raise SessionSealDenied("kernel peer UID mismatch")
    inventory = _socket_inventory()
    if (set(inventory) != {s.fileno() for s in streams}
            or len(set(inventory.values())) != 4):
        raise SessionSealDenied("unexpected inherited or duplicate socket")
    _required(_r25_kernel_prerequisite)
    if (before != (_required(_check_path, snapshot_endpoint, collector_uid),
                   _required(_check_path, witness_endpoint, broker_uid))
            or _socket_inventory() != inventory):
        raise SessionSealDenied("endpoint or FD changed before sealing")
    _required(_load_filter)  # R26's irreversible socket/connect/FD-transfer deny list
    for op in (lambda: socket.socket(socket.AF_UNIX, socket.SOCK_STREAM),
               lambda: socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)):
        try:
            created = op()
        except OSError as exc:
            if exc.errno == errno.EPERM:
                continue
        else:
            for s in created if isinstance(created, tuple) else (created,):
                s.close()
        raise SessionSealDenied("kernel did not enforce post-connect seal")
    if _socket_inventory() != inventory:
        raise SessionSealDenied("FD inventory changed after seal")
    return SealedObserverQueries(streams, approved_snapshot, pause_checker)


class SealedObserverQueries:
    """Drop-in B1 observe_via_snapshots callbacks; exact one-use ordering."""
    receipt = "four_role_pinned_sessions_sealed_not_host_attestation"
    MAX_FRAME = 8192

    def __init__(self, streams, approved, pause_checker):
        self._streams = streams
        self._approved = dict(approved)
        self._pause = pause_checker
        self._step = 0
        self._terminal = False
        self._lock = threading.Lock()
        self._witness = {
            "op": "observe_source", "sender_id": approved["source_id"],
            "origin_turn_id": approved["origin_turn_id"],
            "conversation_id": approved["target_id"],
            "message_id": approved["message_id"],
            "payload_sha256": approved["payload_sha256"],
            "source_command": (f"BATON_WAKE {approved['target_id']} "
                               f"{approved['message_id']} sha256:{approved['payload_sha256']}"),
        }

    def snapshot_query(self, req):
        return self._query(req, witness=False)

    def witness_query(self, req):
        return self._query(req, witness=True)

    def _query(self, req, *, witness):
        with self._lock:
            expected = self._witness if witness else self._approved
            if (self._terminal or self._step not in ((2,) if witness else (0, 1, 3))
                    or type(req) is not dict or req != expected
                    or any(type(v) is not str for v in req.values())):
                raise SessionSealDenied("wrong role, order or approved payload")
            try:
                clear = self._pause() is False
            except Exception as exc:
                self._terminal = True
                raise SessionSealDenied("pause status unknown") from exc
            if not clear:
                self._terminal = True
                raise SessionSealDenied("PAUSE_UI_WRITES active or ambiguous")
            sock = self._streams[(0, 1, 3, 2)[self._step]]
            self._step += 1  # spend before any possible write
            try:
                raw = (json.dumps(req, sort_keys=True, separators=(",", ":"),
                                  allow_nan=False) + "\n").encode("utf-8")
                if len(raw) > self.MAX_FRAME:
                    raise ValueError("oversized request")
                sock.settimeout(3)
                sock.sendall(raw)
                sock.shutdown(socket.SHUT_WR)
                reply = bytearray()
                deadline = time.monotonic() + 3
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError("absolute broker deadline")
                    sock.settimeout(remaining)
                    part = sock.recv(min(4096, self.MAX_FRAME + 1 - len(reply)))
                    if not part:
                        break
                    reply.extend(part)
                    if len(reply) > self.MAX_FRAME:
                        raise ValueError("oversized broker reply")
                if not reply.endswith(b"\n") or reply.count(b"\n") != 1:
                    raise ValueError("missing or ambiguous reply")
                def unique(pairs):
                    out = {}
                    for key, value in pairs:
                        if key in out:
                            raise ValueError("duplicate response key")
                        out[key] = value
                    return out
                result = json.loads(reply[:-1].decode("utf-8"),
                                    object_pairs_hook=unique,
                                    parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
                if type(result) is not dict or type(result.get("state")) is not str:
                    raise ValueError("invalid broker state")
                if self._pause() is not False:
                    raise PermissionError("pause changed after possible commit")
                return result
            except Exception as exc:
                self._terminal = True
                raise SessionUncertain("outcome uncertain; never retry") from exc
            finally:
                sock.close()
