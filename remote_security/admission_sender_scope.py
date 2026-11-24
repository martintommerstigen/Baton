"""B5/B2: kernel-UID-scoped B1 admission *claims*, not ChatGPT authorship.

This opt-in wrapper does not open sockets, browsers, or send messages. B1's
socket handler must call ``request_from_socket(accepted_socket, request)``
INSTEAD OF ``request(request)``. Using the wrapper through the old API fails
closed. SO_PEERCRED authenticates the local process UID, never the asserted
ChatGPT conversation or source turn.
"""
from dataclasses import dataclass
import os
import re
import socket
import struct
from types import MappingProxyType

ID = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
FIELDS = frozenset({"conversation_id", "message_id", "origin_turn_id",
                    "sender_id", "payload_sha256"})


def _uid(value):
    return type(value) is int and value > 0


def _id(value):
    return type(value) is str and ID.fullmatch(value) is not None


def kernel_uid(accepted_socket):
    """Only accepted Linux AF_UNIX sockets can supply this identity."""
    if (not hasattr(socket, "SO_PEERCRED") or
            not isinstance(accepted_socket, socket.socket) or
            accepted_socket.family != socket.AF_UNIX):
        raise ValueError("Linux AF_UNIX peer credentials required")
    fmt = "3i"
    raw = accepted_socket.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED,
                                     struct.calcsize(fmt))
    if len(raw) != struct.calcsize(fmt):
        raise ValueError("incomplete kernel credentials")
    pid, uid, _gid = struct.unpack(fmt, raw)
    if pid <= 0 or uid < 0:
        raise ValueError("invalid kernel peer identity")
    return uid


@dataclass(frozen=True)
class Decision:
    permitted: bool
    reason: str


class SenderScopePolicy:
    """Immutable explicit local process→asserted sender allowlist.

    Each sender gets its own UID; the UI controller and service get different
    UIDs. A sender may target only explicitly enumerated existing chats. This
    does NOT authenticate the source-turn claim; that needs independent UI
    observation in B1 before a real existing-chat wake can be verified.
    """
    def __init__(self, *, broker_uid, controller_uid, sender_uids, allowed_targets, sender_routes):
        if not _uid(broker_uid) or not _uid(controller_uid) or broker_uid == controller_uid:
            raise ValueError("distinct positive broker/controller UIDs required")
        if type(sender_uids) is not dict or not sender_uids:
            raise ValueError("nonempty explicit UID→sender mapping required")
        if type(allowed_targets) not in (set, frozenset) or not allowed_targets:
            raise ValueError("explicit nonempty target allowlist required")
        if any(not _id(target) for target in allowed_targets):
            raise ValueError("invalid target")
        if any(not _uid(uid) or not _id(sender) for uid, sender in sender_uids.items()):
            raise ValueError("invalid sender binding")
        if (broker_uid in sender_uids or controller_uid in sender_uids or
                len(set(sender_uids.values())) != len(sender_uids)):
            raise ValueError("UID roles and sender identities must be distinct")
        if type(sender_routes) is not dict or set(sender_routes) != set(sender_uids.values()):
            raise ValueError("each sender requires explicit route allowlist")
        if any(type(routes) not in (set, frozenset) or not routes or
               any(target not in allowed_targets for target in routes)
               for routes in sender_routes.values()):
            raise ValueError("invalid sender route")
        self.broker_uid = broker_uid
        self.controller_uid = controller_uid
        self.sender_uids = MappingProxyType(dict(sender_uids))
        self.allowed_targets = frozenset(allowed_targets)
        self.sender_routes = MappingProxyType({k:frozenset(v) for k,v in sender_routes.items()})

    def decide(self, peer_uid, req):
        if type(peer_uid) is not int or peer_uid < 0:
            return Decision(False, "invalid_peer_uid")
        if type(req) is not dict or type(req.get("op")) is not str:
            return Decision(False, "invalid_request")
        op = req["op"]
        if op not in ("admit", "begin_click", "status", "pause"):
            return Decision(False, "unsupported_operation")
        if op in ("status", "pause"):
            if set(req) != {"op"}:
                return Decision(False, "unexpected_fields")
            if op == "pause":
                return Decision(peer_uid == self.controller_uid,
                                "controller_only" if peer_uid != self.controller_uid else "controller_scoped")
            allowed = peer_uid == self.controller_uid or peer_uid in self.sender_uids
            return Decision(allowed, "authorized_local_status" if allowed else "unknown_peer_uid")
        if set(req) != FIELDS | {"op"}:
            return Decision(False, "invalid_envelope")
        if any(not _id(req[k]) for k in FIELDS - {"payload_sha256"}):
            return Decision(False, "invalid_envelope")
        if type(req["payload_sha256"]) is not str or not SHA256.fullmatch(req["payload_sha256"]):
            return Decision(False, "invalid_envelope")
        if req["conversation_id"] not in self.allowed_targets:
            return Decision(False, "target_not_allowlisted")
        if op == "admit":
            expected = self.sender_uids.get(peer_uid)
            if expected is None or expected != req["sender_id"]:
                return Decision(False, "sender_uid_mismatch")
            if req["conversation_id"] not in self.sender_routes[expected]:
                return Decision(False, "sender_target_route_denied")
            return Decision(True, "uid_scoped_claim_only")
        # B1 still checks exact admitted envelope, durable click transition and
        # PAUSE_UI_WRITES. This gate never authorizes an actual UI Send.
        return Decision(peer_uid == self.controller_uid,
                        "controller_only" if peer_uid != self.controller_uid else "controller_scoped")


class AuthenticatedAdmissionProxy:
    """Fail-closed adapter for a B1 AdmissionStore-compatible request method.

    B1's handler integration MUST change its dispatch to:
        result = self.server.store.request_from_socket(self.request, req)
    The existing B1 broker allowed_uids must also be a subset of policy UIDs.
    Never expose ``inner`` to an untrusted caller; run as a distinct broker UID.
    """
    def __init__(self, inner, policy):
        if not isinstance(policy, SenderScopePolicy) or not callable(getattr(inner, "request", None)):
            raise TypeError("explicit policy and B1-compatible store required")
        if os.geteuid() != policy.broker_uid:
            raise PermissionError("broker process UID differs from configured service UID")
        self._inner = inner
        self.policy = policy

    def request(self, _req):
        raise PermissionError("unscoped admission request forbidden; pass accepted AF_UNIX socket")

    def request_from_socket(self, accepted_socket, req):
        if os.geteuid() != self.policy.broker_uid:
            return {"state": "rejected", "reason": "broker_uid_changed"}
        try:
            uid = kernel_uid(accepted_socket)
        except (OSError, ValueError, TypeError):
            return {"state": "rejected", "reason": "missing_kernel_peer"}
        decision = self.policy.decide(uid, req)
        if not decision.permitted:
            return {"state": "rejected", "reason": decision.reason}
        return self._inner.request(req)
