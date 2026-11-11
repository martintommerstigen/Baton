"""Baton channel outbox: drafts and owner-approved pending sends.

No platform request is sent until an explicitly configured transport adapter
performs it. A queued draft is not delivery, read, or recipient acceptance.
Distinct event IDs and provenance survive retries, without claiming receipt.
"""
import json
from pathlib import Path
import sqlite3
import time
from uuid import uuid4

KINDS = frozenset({"model", "email", "chat", "social", "forum"})
STATES = frozenset({"draft", "approved", "attempted", "delivered", "failed"})


def create_store(path):
    path = Path(path)
    if path.is_symlink():
        raise ValueError("outbox db symlink not allowed")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    conn = sqlite3.connect(path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS messages (
          message_id TEXT PRIMARY KEY,
          channel_kind TEXT NOT NULL,
          recipient TEXT NOT NULL,
          body TEXT NOT NULL,
          origin TEXT NOT NULL,
          created_at INTEGER NOT NULL,
          state TEXT NOT NULL,
          delivery_proof TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS events (
          event_id TEXT PRIMARY KEY,
          message_id TEXT NOT NULL,
          happened_at INTEGER NOT NULL,
          action TEXT NOT NULL,
          detail TEXT NOT NULL,
          FOREIGN KEY (message_id) REFERENCES messages(message_id)
        )
    """)
    conn.commit()
    return conn


def _event(conn, mid, action, detail):
    conn.execute(
        "INSERT INTO events (event_id,message_id,happened_at,action,detail) VALUES (?,?,?,?,?)",
        (uuid4().hex, mid, time.time_ns(), action, detail)
    )


def draft_message(conn, channel_kind, recipient, body, origin):
    if channel_kind not in KINDS:
        raise ValueError("unsupported channel")
    for value, bound in ((recipient, 300), (body, 12000), (origin, 250)):
        if not isinstance(value, str) or not value.strip() or len(value) > bound:
            raise ValueError("invalid message field")
    mid = uuid4().hex
    with conn:
        conn.execute("""INSERT INTO messages
             (message_id,channel_kind,recipient,body,origin,created_at,state)
             VALUES (?,?,?,?,?,?,?)""",
             (mid, channel_kind, recipient, body, origin, time.time_ns(), "draft"))
        _event(conn, mid, "drafted", "not-delivered")
    return mid


def approve_message(conn, message_id):
    """Approval authorizes an adapter to attempt; it does not claim delivery."""
    with conn:
        changed = conn.execute(
            "UPDATE messages SET state='approved' WHERE message_id=? AND state='draft'",
            (message_id,)
        ).rowcount
        if changed != 1:
            raise ValueError("draft missing or already approved")
        _event(conn, message_id, "owner-approved", "not-sent")


def mark_attempted(conn, message_id, adapter):
    """Only call from an actual authenticated channel adapter before its send."""
    if not isinstance(adapter, str) or not adapter.strip():
        raise ValueError("adapter identity required")
    with conn:
        changed = conn.execute(
            "UPDATE messages SET state='attempted' WHERE message_id=? AND state='approved'",
            (message_id,)
        ).rowcount
        if changed != 1:
            raise ValueError("not approved or already attempted")
        _event(conn, message_id, "send-attempted", adapter)


def record_transport_outcome(conn, message_id, *, success, proof):
    """A transport acknowledgement is not a recipient read or a model reply."""
    if not isinstance(proof, str) or not proof.strip() or len(proof) > 1000:
        raise ValueError("transport receipt/error required")
    state = "delivered" if success else "failed"
    with conn:
        changed = conn.execute(
            "UPDATE messages SET state=?,delivery_proof=? WHERE message_id=? AND state='attempted'",
            (state, proof, message_id)
        ).rowcount
        if changed != 1:
            raise ValueError("no outstanding send attempt")
        _event(conn, message_id, "transport-" + state, proof)


def get_messages(conn, limit=50):
    if not isinstance(limit, int) or not 1 <= limit <= 200:
        raise ValueError("invalid limit")
    rows = conn.execute(
        "SELECT message_id,channel_kind,recipient,body,origin,created_at,state,delivery_proof "
        "FROM messages ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()
    columns = ("message_id","channel_kind","recipient","body","origin",
               "created_at","state","delivery_proof")
    return [dict(zip(columns, row)) for row in rows]


def get_events(conn, message_id):
    return conn.execute(
        "SELECT action,detail FROM events WHERE message_id=? ORDER BY happened_at,event_id",
        (message_id,)
    ).fetchall()
