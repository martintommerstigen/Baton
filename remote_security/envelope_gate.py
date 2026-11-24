"""Fail-closed Baton Remote envelope gate. No UI, shell, or network side effects.

Acceptance is a durable, *unverified delivery* receipt. It is never a wake.
"""
import hashlib
import hmac
import json
import re
import sqlite3
import time

from remote_security.private_store import connect_private

_ID = re.compile(r"^[a-zA-Z0-9_-]{8,96}$")
_ALLOWED = {"wake_request"}
MAX_PAYLOAD_BYTES = 65536

class Rejected(ValueError):
    pass

class Gate:
    def __init__(self, database, keys, allowed_senders, allowed_targets, clock=time.time):
        self.database = str(database)
        self.keys = dict(keys)
        self.senders = frozenset(allowed_senders)
        self.targets = frozenset(allowed_targets)
        self.clock = clock
        # Retain the existing .db interface for older callers/tests. Actual
        # accept transactions use independent connections, safe across threads.
        self.db = connect_private(self.database)
        self.db.execute("CREATE TABLE IF NOT EXISTS receipts (sender TEXT NOT NULL, msg TEXT NOT NULL, digest TEXT NOT NULL, state TEXT NOT NULL, PRIMARY KEY(sender,msg))")
        self.db.execute("CREATE TABLE IF NOT EXISTS payloads (sender TEXT NOT NULL, msg TEXT NOT NULL, envelope BLOB NOT NULL, payload BLOB NOT NULL, signature TEXT NOT NULL, PRIMARY KEY(sender,msg))")

    @staticmethod
    def canonical(envelope):
        return json.dumps(envelope, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")

    @classmethod
    def sign(cls, envelope, secret):
        return hmac.new(secret, cls.canonical(envelope), hashlib.sha256).hexdigest()

    def accept_payload(self, envelope, signature, payload):
        """Bind actual payload bytes before admission; never execute contents."""
        if not isinstance(payload, bytes) or len(payload) > MAX_PAYLOAD_BYTES:
            raise Rejected("payload type or size")
        if not isinstance(envelope, dict) or not isinstance(envelope.get('payload_sha256'), str):
            raise Rejected('schema')
        if not hmac.compare_digest(hashlib.sha256(payload).hexdigest(), envelope['payload_sha256']):
            raise Rejected('payload mismatch')
        return self._accept(envelope, signature, payload)

    def accept(self, envelope, signature):
        """Authenticate envelope only; payload remains UNVERIFIED until bound."""
        return self._accept(envelope, signature, None)

    def _accept(self, envelope, signature, payload):
        if not isinstance(envelope, dict) or set(envelope) != {"version", "sender", "target", "message_id", "issued_at", "action", "payload_sha256"}:
            raise Rejected("schema")
        if type(envelope["version"]) is not int or envelope["version"] != 1:
            raise Rejected("version")
        sender, target, mid = (envelope[k] for k in ("sender", "target", "message_id"))
        if not all(isinstance(v, str) and _ID.fullmatch(v) for v in (sender, target, mid)):
            raise Rejected("identifier")
        if (sender not in self.senders or target not in self.targets
                or not isinstance(envelope["action"], str) or envelope["action"] not in _ALLOWED):
            raise Rejected("policy")
        digest = envelope["payload_sha256"]
        if not isinstance(digest, str) or not re.fullmatch("[0-9a-f]{64}", digest):
            raise Rejected("payload digest")
        ts = envelope["issued_at"]
        if type(ts) is not int or abs(self.clock() - ts) > 60:
            raise Rejected("expired")
        secret = self.keys.get(sender)
        if not isinstance(secret, bytes) or len(secret) < 32 or not isinstance(signature, str):
            raise Rejected("key")
        if not hmac.compare_digest(self.sign(envelope, secret), signature):
            raise Rejected("signature")
        fingerprint = hashlib.sha256(self.canonical(envelope)).hexdigest()
        db = connect_private(self.database)
        try:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute("SELECT digest FROM receipts WHERE sender=? AND msg=?", (sender, mid)).fetchone()
            if existing:
                db.execute("ROLLBACK")
                raise Rejected("replay" if existing[0] == fingerprint else "collision")
            db.execute("INSERT INTO receipts VALUES (?,?,?,?)", (sender, mid, fingerprint, "accepted_not_delivered"))
            if payload is not None:
                # The envelope and exact bytes are persisted in the SAME
                # transaction; no receipt may survive a failed payload write.
                db.execute("INSERT INTO payloads VALUES (?,?,?,?,?)",
                           (sender, mid, self.canonical(envelope), payload, signature))
            db.execute("COMMIT")
        except sqlite3.Error:
            if db.in_transaction:
                db.execute("ROLLBACK")
            raise
        finally:
            db.close()
        return "accepted_not_delivered"
