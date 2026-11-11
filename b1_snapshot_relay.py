"""B1 snapshot-only local relay for an existing ChatGPT source turn.

The collector alone owns a write-capable CDP connection. A separate observer
UID gets only a fixed, authenticated AF_UNIX snapshot operation, never a CDP
handle, arbitrary URL, browser command or shell. This is an observation claim,
not ChatGPT authorship, an actual UI send or a verified A->B->C chain.

Linux SCM_CREDENTIALS enforcement is delegated to Ronja R23; fail closed if
that pinned dependency is absent. Do not install this under a shared CDP UID.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import socketserver
import stat

from chatgpt_ui_driver import CHAT_ID, conversation_id, marker_for

SHA256 = re.compile(r"^[0-9a-f]{64}$")
SNAPSHOT_KEYS = frozenset({"op", "source_id", "origin_turn_id", "target_id",
                           "message_id", "payload_sha256"})


class SnapshotUncertain(RuntimeError):
    """A witness may already be committed; never automatically retry it."""


def _validate_request(req, source_id):
    if type(req) is not dict or set(req) != SNAPSHOT_KEYS or req["op"] != "snapshot":
        raise PermissionError("snapshot-only exact schema required")
    if (any(type(req[k]) is not str or not CHAT_ID.fullmatch(req[k])
            for k in ("source_id", "target_id"))
            or req["source_id"] != source_id
            or req["source_id"] == req["target_id"]):
        raise PermissionError("source/target route denied")
    if (type(req["origin_turn_id"]) is not str
            or not req["origin_turn_id"].strip()
            or len(req["origin_turn_id"]) > 128):
        raise ValueError("invalid source turn ID")
    marker_for(req["message_id"])
    if type(req["payload_sha256"]) is not str or not SHA256.fullmatch(req["payload_sha256"]):
        raise ValueError("invalid approved payload digest")


def make_snapshot(reader, req, *, source_id, allowed_targets, pause_checker):
    """Two exact DOM reads, no mutation, fixed existing source UUID.

    The caller must isolate the collector's CDP access from the observer UID.
    Even an authentic collector response is not cryptographic ChatGPT identity.
    """
    _validate_request(req, source_id)
    if (type(allowed_targets) not in (set, frozenset) or not allowed_targets
            or any(type(t) is not str or not CHAT_ID.fullmatch(t)
                   or t == source_id for t in allowed_targets)
            or req["target_id"] not in allowed_targets):
        raise PermissionError("target not on fixed collector route allowlist")
    if not callable(pause_checker) or pause_checker() is not False:
        raise PermissionError("PAUSE_UI_WRITES active or untrusted")
    expected = (f"BATON_WAKE {req['target_id']} {req['message_id']} "
                f"sha256:{req['payload_sha256']}")
    urls = []
    for _ in range(2):
        url = reader.page.url
        if conversation_id(url) != source_id or reader.is_generating(source_id):
            raise PermissionError("source tab changed or response still generating")
        if reader.read_assistant_turn(source_id, req["origin_turn_id"]) != expected:
            raise PermissionError("source turn not exact standalone command")
        urls.append(url)
    if (urls[0] != urls[1] or pause_checker() is not False
            or reader.is_generating(source_id)):
        raise PermissionError("source or pause changed during snapshot")
    return {"state": "source_snapshot_not_authorship", "source_id": source_id,
            "origin_turn_id": req["origin_turn_id"],
            "source_url": f"https://chatgpt.com/c/{source_id}",
            "source_text_sha256": hashlib.sha256(expected.encode("utf-8")).hexdigest()}


def _unique_pairs(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError("duplicate JSON key")
        obj[key] = value
    return obj


def _secure_new_socket_path(path):
    raw = os.fspath(path)
    if type(raw) is not str or not raw.startswith("/") or any(
            p in ("", ".", "..") for p in raw.split("/")[1:]):
        raise PermissionError("absolute canonical Unix-socket path required")
    target = Path(raw)
    parent = Path("/")
    for part in target.parent.parts[1:]:
        parent = parent / part
        info = parent.lstat()
        if not stat.S_ISDIR(info.st_mode):
            raise PermissionError("symlink/non-directory socket ancestor")
        if info.st_mode & 0o022 and not (
                info.st_uid == 0 and info.st_mode & stat.S_ISVTX):
            raise PermissionError("writable socket ancestor")
    info = target.parent.lstat()
    if info.st_uid != os.geteuid() or info.st_mode & 0o022:
        raise PermissionError("collector must own non-writable socket directory")
    try:
        target.lstat()
    except FileNotFoundError:
        return raw
    raise PermissionError("refusing preexisting socket path or symlink")


class SnapshotHandler(socketserver.BaseRequestHandler):
    def handle(self):
        try:
            # Ronja R23 enforces the *writer* PID/UID on each recvmsg segment;
            # SO_PEERCRED alone would accept a delegated descriptor.
            from remote_security.frame_credentials import read_authenticated_frame
            frame, _uid = read_authenticated_frame(
                self.request, allowed_uids=frozenset({self.server.observer_uid}))
            req = json.loads(frame.decode("utf-8"), object_pairs_hook=_unique_pairs,
                             parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
            if not self.server.endpoint_unchanged():
                return
            result = make_snapshot(self.server.reader, req,
                                   source_id=self.server.source_id,
                                   allowed_targets=self.server.allowed_targets,
                                   pause_checker=self.server.pause_checker)
            if not self.server.endpoint_unchanged():
                return
            self.request.sendall((json.dumps(result, sort_keys=True, allow_nan=False)
                                  + "\n").encode("utf-8"))
        except (ImportError, OSError, RuntimeError, PermissionError, ValueError,
                TypeError, UnicodeError, AttributeError):
            # Silence is failure, not an affirmative receipt. Never retry a
            # possibly committed downstream witness automatically.
            return


class SnapshotServer(socketserver.UnixStreamServer):
    allow_reuse_address = False

    def __init__(self, path, *, reader, source_id, allowed_targets,
                 observer_uid, pause_checker):
        if (os.geteuid() == 0 or type(observer_uid) is not int
                or observer_uid <= 0 or observer_uid == os.geteuid()):
            raise PermissionError("separate non-root collector/observer UIDs required")
        if type(source_id) is not str or not CHAT_ID.fullmatch(source_id):
            raise ValueError("fixed existing ChatGPT source UUID required")
        if (type(allowed_targets) not in (set, frozenset) or not allowed_targets
                or any(type(t) is not str or not CHAT_ID.fullmatch(t)
                       or t == source_id for t in allowed_targets)):
            raise ValueError("fixed target UUID allowlist required")
        if not callable(pause_checker):
            raise TypeError("trusted pause callback required")
        path = _secure_new_socket_path(path)
        self.reader = reader
        self.source_id = source_id
        self.allowed_targets = frozenset(allowed_targets)
        self.observer_uid = observer_uid
        self.pause_checker = pause_checker
        super().__init__(path, SnapshotHandler, bind_and_activate=False)
        try:
            from remote_security.frame_credentials import enable_listener_credentials
            enable_listener_credentials(self.socket)
            self.server_bind()
            self.server_activate()
            os.chmod(path, 0o660)
            info = os.lstat(path)
            self.socket_identity = (info.st_dev, info.st_ino)
        except BaseException:
            self.server_close()
            raise

    def endpoint_unchanged(self):
        try:
            info = os.lstat(self.server_address)
            return (stat.S_ISSOCK(info.st_mode)
                    and info.st_uid == os.geteuid()
                    and (info.st_dev, info.st_ino) == self.socket_identity
                    and not (info.st_mode & 0o002))
        except OSError:
            return False


def snapshot_request(source, source_turn_id, target, message_id, payload_sha256):
    req = {"op": "snapshot", "source_id": source,
           "origin_turn_id": source_turn_id, "target_id": target,
           "message_id": message_id, "payload_sha256": payload_sha256}
    _validate_request(req, source)
    return req


def observe_via_snapshots(*, source, source_turn_id, target, message_id,
                          payload_sha256, snapshot_query, witness_query,
                          pause_checker):
    """Observer-UID witness bridge with NO browser/CDP object or UI Send.

    Both query callbacks must authenticate separate Linux peer UIDs before
    sending; a forged collector can still fabricate a snapshot claim.
    """
    req = snapshot_request(source, source_turn_id, target, message_id,
                           payload_sha256)
    if not all(callable(x) for x in (snapshot_query, witness_query, pause_checker)):
        raise TypeError("authenticated query and pause callbacks required")
    command = f"BATON_WAKE {target} {message_id} sha256:{payload_sha256}"
    expected = {"state": "source_snapshot_not_authorship", "source_id": source,
                "origin_turn_id": source_turn_id,
                "source_url": f"https://chatgpt.com/c/{source}",
                "source_text_sha256": hashlib.sha256(command.encode("utf-8")).hexdigest()}

    def check():
        if pause_checker() is not False:
            raise PermissionError("PAUSE_UI_WRITES active or untrusted")
        result = snapshot_query(dict(req))
        if type(result) is not dict or set(result) != set(expected):
            raise PermissionError("untrusted snapshot schema")
        if any(result[k] != expected[k] for k in expected if k != "source_url"):
            raise PermissionError("source snapshot mismatch")
        if conversation_id(result["source_url"]) != source:
            raise PermissionError("source snapshot URL mismatch")
        if pause_checker() is not False:
            raise PermissionError("pause changed after snapshot")

    check()
    check()
    witness = {"op": "observe_source", "sender_id": source,
               "origin_turn_id": source_turn_id, "conversation_id": target,
               "message_id": message_id, "payload_sha256": payload_sha256,
               "source_command": command}
    try:
        result = witness_query(witness)
    except Exception as exc:
        raise SnapshotUncertain("witness outcome unknown; no automatic retry") from exc
    try:
        check()
    except Exception as exc:
        raise SnapshotUncertain("source changed after possible witness commit") from exc
    if result != {"state": "source_observation_recorded_not_authorship"}:
        raise SnapshotUncertain("witness not confirmed; reconcile, never blind retry")
    return {"state": "source_observation_recorded_not_authorship",
            "classification": "snapshot_observation_not_chatgpt_authorship"}
