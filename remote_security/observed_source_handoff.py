"""B5/B2: one-use observed-source handoff for B1's existing-chat UI controller.

A ChatGPT conversation is NOT a Linux process or a sender UID. An explicitly
authorized *read-only source observer* (distinct UID) may register its claim
about one source turn. A distinct UI controller may then spend that exact
claim to request B1 admission. This is an observation CLAIM, not independent
proof of ChatGPT authorship or permission to click Send.

No browser, network listener, shell, UI write, retry or retirement is here.
The inner B1 AdmissionStore alone controls PAUSE_UI_WRITES, target admission
and the durable begin_click -> uncertain transition.
"""
from contextlib import closing
import hashlib
import os
import re
import sqlite3
from types import MappingProxyType

from remote_security.admission_sender_scope import kernel_uid

IDENT = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
DIGEST = re.compile(r"^[0-9a-f]{64}$")
ENVELOPE = frozenset({"conversation_id", "message_id", "origin_turn_id",
                      "sender_id", "payload_sha256"})
OBSERVED = ENVELOPE | {"source_command"}
SCHEMA = """
CREATE TABLE IF NOT EXISTS b5_source_witness_v1 (
 sender_id TEXT NOT NULL,
 origin_turn_id TEXT NOT NULL,
 conversation_id TEXT NOT NULL,
 message_id TEXT NOT NULL UNIQUE,
 payload_sha256 TEXT NOT NULL,
 source_text_sha256 TEXT NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('witnessed','spent')),
 witnessed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 spent_at TEXT,
 PRIMARY KEY(sender_id,origin_turn_id)
);
"""


def _uid(value):
    return type(value) is int and value > 0


def _ident(value):
    return type(value) is str and IDENT.fullmatch(value) is not None


def _digest(value):
    return type(value) is str and DIGEST.fullmatch(value) is not None


class ObservedSourceHandoff:
    """Opt-in B1 store adapter; B1 handler calls request_from_socket.

    The source observer is a read-only *process role*, not a fabricated
    ChatGPT A/B process. Its claimed UI observation must be independently
    checked against the real source turn by B1's live UI driver. A kernel
    credential cannot prove an actual ChatGPT assistant response.

    Witness and B1 admission use the SAME B1 SQLite database, but two
    transactions. Witness is committed as spent BEFORE invoking B1 admission:
    a crash can permanently lose a witness, never silently duplicate a send.
    No retry is safe or automatic after uncertain delivery.
    """

    def __init__(self, inner, *, broker_uid, observer_uid, controller_uid,
                 source_routes):
        if not all(map(_uid, (broker_uid, observer_uid, controller_uid))):
            raise ValueError("distinct non-root UID roles required")
        if len({broker_uid, observer_uid, controller_uid}) != 3:
            raise ValueError("broker, observer and controller must be distinct")
        if os.geteuid() != broker_uid:
            raise PermissionError("broker effective UID mismatch")
        if (not callable(getattr(inner, "connect", None)) or
                not callable(getattr(inner, "request", None)) or
                not isinstance(getattr(inner, "allowed", None), (set, frozenset))):
            raise TypeError("actual B1-compatible SQLite AdmissionStore required")
        if type(source_routes) is not dict or not source_routes:
            raise ValueError("explicit source-to-target routes required")
        allowed = frozenset(inner.allowed)
        routes = {}
        for sender, targets in source_routes.items():
            if not _ident(sender) or type(targets) not in (set, frozenset) or not targets:
                raise ValueError("invalid source route")
            if any(not _ident(t) or t == sender or t not in allowed for t in targets):
                raise ValueError("route not in B1 target allowlist")
            routes[sender] = frozenset(targets)
        self.broker_uid = broker_uid
        self.observer_uid = observer_uid
        self.controller_uid = controller_uid
        self.routes = MappingProxyType(routes)
        self._inner = inner
        with closing(self._inner.connect()) as db:
            db.executescript(SCHEMA)

    def request(self, _req):
        raise PermissionError("unscoped B1 request is forbidden")

    def _valid(self, req, keys):
        if type(req) is not dict or set(req) != keys | {"op"}:
            return False
        if any(not _ident(req[k]) for k in ENVELOPE - {"payload_sha256"}):
            return False
        if not _digest(req["payload_sha256"]):
            return False
        sender, target = req["sender_id"], req["conversation_id"]
        if "source_command" in keys:
            # Match B1 H20's actual exact-command grammar; an arbitrary digest
            # or a quoted/example command is not a source-turn witness.
            expected = (f"BATON_WAKE {target} {req['message_id']} "
                        f"sha256:{req['payload_sha256']}")
            if type(req["source_command"]) is not str or req["source_command"] != expected:
                return False
        return sender in self.routes and target in self.routes[sender]

    def _record_observation(self, req):
        with closing(self._inner.connect()) as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                try:
                    db.execute("""INSERT INTO b5_source_witness_v1
                      (sender_id,origin_turn_id,conversation_id,message_id,
                       payload_sha256,source_text_sha256,state)
                      VALUES (?,?,?,?,?,?,'witnessed')""",
                      (req["sender_id"], req["origin_turn_id"],
                       req["conversation_id"], req["message_id"],
                       req["payload_sha256"],
                       hashlib.sha256(req["source_command"].encode("utf-8")).hexdigest()))
                    result = {"state": "source_observation_recorded_not_authorship"}
                except sqlite3.IntegrityError:
                    result = {"state": "rejected", "reason": "observation_replay"}
                db.execute("COMMIT")
                return result
            except BaseException:
                db.execute("ROLLBACK")
                raise

    def _spend_before_admission(self, req):
        with closing(self._inner.connect()) as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                row = db.execute("""SELECT conversation_id,message_id,
                    payload_sha256,state FROM b5_source_witness_v1
                    WHERE sender_id=? AND origin_turn_id=?""",
                    (req["sender_id"], req["origin_turn_id"])).fetchone()
                expected = (req["conversation_id"], req["message_id"],
                            req["payload_sha256"], "witnessed")
                if row is None:
                    result = {"state": "rejected", "reason": "no_source_observation"}
                elif row != expected:
                    result = {"state": "rejected", "reason": "observation_mismatch_or_spent"}
                else:
                    db.execute("""UPDATE b5_source_witness_v1
                        SET state='spent', spent_at=CURRENT_TIMESTAMP
                        WHERE sender_id=? AND origin_turn_id=? AND state='witnessed'""",
                        (req["sender_id"], req["origin_turn_id"]))
                    result = None
                db.execute("COMMIT")
            except BaseException:
                db.execute("ROLLBACK")
                raise
        if result is not None:
            return result
        # B1 is authoritative for PAUSE_UI_WRITES, exact target admission,
        # global source/message replay and durable begin_click uncertainty.
        # If B1 fails or the broker dies here, the witness stays spent.
        return self._inner.request(req)

    def request_from_socket(self, accepted_socket, req):
        if os.geteuid() != self.broker_uid:
            return {"state": "rejected", "reason": "broker_uid_changed"}
        try:
            uid = kernel_uid(accepted_socket)
        except (OSError, ValueError, TypeError):
            return {"state": "rejected", "reason": "missing_kernel_peer"}
        if type(req) is not dict or type(req.get("op")) is not str:
            return {"state": "rejected", "reason": "invalid_request"}
        op = req["op"]
        if op == "observe_source":
            if uid != self.observer_uid:
                return {"state": "rejected", "reason": "observer_only"}
            if not self._valid(req, OBSERVED):
                return {"state": "rejected", "reason": "invalid_observation_or_route"}
            return self._record_observation(req)
        if op == "admit":
            if uid != self.controller_uid:
                return {"state": "rejected", "reason": "controller_only"}
            if not self._valid(req, ENVELOPE):
                return {"state": "rejected", "reason": "invalid_envelope_or_route"}
            return self._spend_before_admission(req)
        if op in ("begin_click", "pause", "status"):
            if uid not in ({self.observer_uid, self.controller_uid}
                           if op == "status" else {self.controller_uid}):
                return {"state": "rejected", "reason": "controller_only"}
            if op == "begin_click":
                if not self._valid(req, ENVELOPE):
                    return {"state": "rejected", "reason": "invalid_envelope_or_route"}
            elif set(req) != {"op"}:
                return {"state": "rejected", "reason": "unexpected_fields"}
            return self._inner.request(req)
        return {"state": "rejected", "reason": "unsupported_operation"}
