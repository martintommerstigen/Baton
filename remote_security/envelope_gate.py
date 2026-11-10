"""Fail-closed Baton Remote envelope gate. No UI, shell, or network side effects."""
import hashlib
import hmac
import json
import re
import sqlite3
import time

_ID = re.compile(r"^[a-zA-Z0-9_-]{8,96}$")
_ALLOWED = {"wake_request"}

class Rejected(ValueError):
    pass

class Gate:
    def __init__(self, database, keys, allowed_senders, allowed_targets, clock=time.time):
        self.keys = keys
        self.senders = frozenset(allowed_senders)
        self.targets = frozenset(allowed_targets)
        self.clock = clock
        self.db = sqlite3.connect(database, isolation_level=None, timeout=10)
        self.db.execute("PRAGMA busy_timeout=10000")
        self.db.execute("CREATE TABLE IF NOT EXISTS receipts (sender TEXT NOT NULL, msg TEXT NOT NULL, digest TEXT NOT NULL, state TEXT NOT NULL, PRIMARY KEY(sender,msg))")

    @staticmethod
    def canonical(envelope):
        return json.dumps(envelope, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")

    @classmethod
    def sign(cls, envelope, secret):
        return hmac.new(secret, cls.canonical(envelope), hashlib.sha256).hexdigest()

    def accept(self, envelope, signature):
        if not isinstance(envelope, dict) or set(envelope) != {"version", "sender", "target", "message_id", "issued_at", "action", "payload_sha256"}:
            raise Rejected("schema")
        if type(envelope["version"]) is not int or envelope["version"] != 1:
            raise Rejected("version")
        sender, target, mid = (envelope[k] for k in ("sender", "target", "message_id"))
        if not all(isinstance(v, str) and _ID.fullmatch(v) for v in (sender, target, mid)):
            raise Rejected("identifier")
        if sender not in self.senders or target not in self.targets or envelope["action"] not in _ALLOWED:
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
        try:
            self.db.execute("BEGIN IMMEDIATE")
            existing = self.db.execute("SELECT digest FROM receipts WHERE sender=? AND msg=?", (sender, mid)).fetchone()
            if existing:
                self.db.execute("ROLLBACK")
                raise Rejected("replay" if existing[0] == fingerprint else "collision")
            self.db.execute("INSERT INTO receipts VALUES (?,?,?,?)", (sender, mid, fingerprint, "accepted_not_delivered"))
            self.db.execute("COMMIT")
        except sqlite3.Error:
            if self.db.in_transaction:
                self.db.execute("ROLLBACK")
            raise
        return "accepted_not_delivered"
