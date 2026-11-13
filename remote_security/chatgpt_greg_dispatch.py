"""Authenticated Baton job dispatch to the local Greg executor.

This is a callable adapter, not a ChatGPT connector. An external ChatGPT
integration must transport the signed request to this trusted local process.
Never treat an asserted conversation_id as authenticated model identity.
"""
import hashlib
import hmac
import json
import sqlite3
import time
from remote_security.greg_executor_client import run_local

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False).encode("ascii")

class AuthenticatedGregDispatcher:
    def __init__(self, database, secret, socket_path, allowed_conversations, allowed_commands,
                 clock=time.time, transport=run_local):
        if type(secret) is not bytes or len(secret) < 32:
            raise ValueError("32+ byte shared secret required")
        if not allowed_conversations or not allowed_commands:
            raise ValueError("explicit conversation and executable allowlists required")
        self.database, self.secret, self.socket_path = database, secret, socket_path
        self.conversations = frozenset(allowed_conversations)
        self.commands = frozenset(allowed_commands)
        self.clock, self.transport = clock, transport
        with sqlite3.connect(database) as db:
            db.execute("""CREATE TABLE IF NOT EXISTS greg_jobs(
                id TEXT PRIMARY KEY, digest TEXT NOT NULL, state TEXT NOT NULL,
                receipt TEXT)""")

    def sign(self, request):
        return hmac.new(self.secret, canonical(request), hashlib.sha256).hexdigest()

    def dispatch(self, request, signature):
        if type(request) is not dict or set(request) != {
            "job_id", "conversation_id", "issued_at", "argv"}:
            raise ValueError("invalid job schema")
        job_id, conversation_id, issued, argv = (
            request[k] for k in ("job_id", "conversation_id", "issued_at", "argv"))
        if (type(job_id) is not str or not 8 <= len(job_id) <= 96 or
            not all(c.isalnum() or c in "-_" for c in job_id)):
            raise ValueError("invalid job ID")
        if conversation_id not in self.conversations:
            raise PermissionError("conversation not allowlisted")
        if type(issued) is not int or abs(self.clock()-issued)>60:
            raise ValueError("expired request")
        if (type(argv) is not list or not argv or type(argv[0]) is not str
            or argv[0] not in self.commands):
            raise PermissionError("executable not allowlisted")
        if type(signature) is not str or not hmac.compare_digest(self.sign(request), signature):
            raise PermissionError("invalid signature")
        digest = hashlib.sha256(canonical(request)).hexdigest()
        # Durable reservation BEFORE execution; a crash leaves uncertainty.
        with sqlite3.connect(self.database, timeout=10) as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT digest,state,receipt FROM greg_jobs WHERE id=?",
                             (job_id,)).fetchone()
            if row:
                if row[0] != digest: raise ValueError("job ID collision")
                return {"state":row[1], "receipt":json.loads(row[2]) if row[2] else None}
            db.execute("INSERT INTO greg_jobs VALUES (?,?,?,NULL)",
                       (job_id,digest,"started_uncertain"))
        try:
            receipt = self.transport(self.socket_path, argv)
        except Exception:
            # No retry: command might have executed before transport failure.
            raise
        with sqlite3.connect(self.database, timeout=10) as db:
            db.execute("UPDATE greg_jobs SET state=?, receipt=? WHERE id=?",
                       (receipt["state"],json.dumps(receipt),job_id))
        return {"state":receipt["state"],"receipt":receipt}
