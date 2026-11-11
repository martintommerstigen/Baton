"""Baton recipient-controlled attention and selective-retention policy.

Core decisions are about *local presentation*, not network delivery or a
person's acceptance. Verified identities must be provider-scoped, not names.
Untrusted sender tags cannot gain access to a recipient allowlist.
"""
from dataclasses import dataclass
from hashlib import sha256
import json
import sqlite3
import time
from uuid import uuid4

DIMENSIONS = frozenset(("identity", "topic", "keyword"))
ACTIONS = frozenset(("allow", "mute", "block"))
MODES = frozenset(("open", "allowlist"))
CHANNELS = frozenset(("model", "chat", "email", "forum", "social"))
VISIBLE_TTL_NS = 7 * 24 * 3600 * 10**9
MUTED_TTL_NS = 24 * 3600 * 10**9
AUDIT_TTL_NS = 30 * 24 * 3600 * 10**9
REPLAY_TTL_NS = 90 * 24 * 3600 * 10**9


def _string(value, length=300):
    if not isinstance(value, str) or not value.strip() or len(value) > length or "\x00" in value:
        raise ValueError("invalid text field")
    return value.strip()


def _owner(value):
    return _string(value, 160)


def _normalize(dimension, value):
    value = _string(value, 250)
    if dimension == "identity":
        # A friendly display name is NOT a stable authenticated identity.
        if ":" not in value or value.startswith(":") or value.endswith(":"):
            raise ValueError("identity must be provider-scoped (provider:stable-id)")
        return value
    return " ".join(value.casefold().split())


def _digest(value):
    return sha256(value.encode("utf-8")).hexdigest()


def setup_attention(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS attention_policy (
        recipient TEXT PRIMARY KEY,
        mode TEXT NOT NULL CHECK(mode IN ('open','allowlist'))
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS attention_rules (
        rule_id TEXT PRIMARY KEY,
        recipient TEXT NOT NULL,
        dimension TEXT NOT NULL,
        pattern TEXT NOT NULL,
        action TEXT NOT NULL,
        UNIQUE(recipient,dimension,pattern)
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS attention_decisions (
        decision_id TEXT PRIMARY KEY,
        recipient TEXT NOT NULL,
        channel TEXT NOT NULL,
        source_digest TEXT NOT NULL,
        sender_digest TEXT NOT NULL,
        sender_verified INTEGER NOT NULL,
        decision TEXT NOT NULL,
        reason TEXT NOT NULL,
        occurred_ns INTEGER NOT NULL,
        UNIQUE(recipient,channel,source_digest)
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS attention_inbox (
        decision_id TEXT PRIMARY KEY,
        recipient TEXT NOT NULL,
        channel TEXT NOT NULL,
        sender_display TEXT NOT NULL,
        body TEXT NOT NULL,
        state TEXT NOT NULL CHECK(state IN ('visible','muted')),
        expires_ns INTEGER NOT NULL
    )""")
    conn.commit()


def set_mode(conn, recipient, mode):
    recipient = _owner(recipient)
    if mode not in MODES:
        raise ValueError("invalid attention mode")
    with conn:
        conn.execute("INSERT INTO attention_policy (recipient,mode) VALUES (?,?) "
                     "ON CONFLICT(recipient) DO UPDATE SET mode=excluded.mode",
                     (recipient, mode))


def get_mode(conn, recipient):
    recipient = _owner(recipient)
    found = conn.execute("SELECT mode FROM attention_policy WHERE recipient=?",
                         (recipient,)).fetchone()
    return found[0] if found else "open"


def set_rule(conn, recipient, dimension, pattern, action):
    recipient = _owner(recipient)
    if dimension not in DIMENSIONS or action not in ACTIONS:
        raise ValueError("invalid attention rule")
    pattern = _normalize(dimension, pattern)
    with conn:
        old = conn.execute(
            "SELECT rule_id FROM attention_rules "
            "WHERE recipient=? AND dimension=? AND pattern=?",
            (recipient, dimension, pattern)).fetchone()
        if old:
            rid = old[0]
            conn.execute("UPDATE attention_rules SET action=? WHERE rule_id=?",
                         (action, rid))
        else:
            rid = uuid4().hex
            conn.execute("INSERT INTO attention_rules "
                         "(rule_id,recipient,dimension,pattern,action) VALUES (?,?,?,?,?)",
                         (rid, recipient, dimension, pattern, action))
    return rid


def remove_rule(conn, recipient, rule_id):
    with conn:
        return bool(conn.execute(
            "DELETE FROM attention_rules WHERE recipient=? AND rule_id=?",
            (_owner(recipient), _string(rule_id, 64))).rowcount)


def list_rules(conn, recipient):
    found = conn.execute(
        "SELECT rule_id,dimension,pattern,action FROM attention_rules "
        "WHERE recipient=? ORDER BY dimension,pattern", (_owner(recipient),)
    ).fetchall()
    return [{"rule_id": r[0], "dimension": r[1], "pattern": r[2],
             "action": r[3]} for r in found]


def decide(conn, recipient, *, sender_id, sender_verified=False,
           topics=(), topics_trusted=False, body=""):
    """Return local pass/mute/block and reason, without any side effects.

    The caller (a real transport adapter) is responsible for verifying
    sender identity and recipient-side classification. Unverified tags can
    cause a block/mute but NEVER satisfy an allowlist.
    """
    recipient = _owner(recipient)
    sender_id = _string(sender_id, 250)
    if type(sender_verified) is not bool or type(topics_trusted) is not bool:
        raise ValueError("verification flags must be boolean")
    if not isinstance(body, str) or len(body) > 12000:
        raise ValueError("invalid body")
    if not isinstance(topics, (tuple, list, set)) or len(topics) > 24:
        raise ValueError("invalid topic labels")
    labels = {_normalize("topic", topic) for topic in topics}
    matches = []
    for rule in list_rules(conn, recipient):
        dimension, pattern, action = rule["dimension"], rule["pattern"], rule["action"]
        matched = (
            (dimension == "identity" and pattern == sender_id)
            or (dimension == "topic" and pattern in labels)
            or (dimension == "keyword" and pattern in body.casefold())
        )
        if not matched:
            continue
        # A claimed identity can be blocked, but cannot grant access.
        trusted_allow = (
            dimension == "identity" and sender_verified
            or dimension == "topic" and topics_trusted
        )
        if action != "allow" or trusted_allow:
            matches.append(rule)
    for action in ("block", "mute"):
        for rule in matches:
            if rule["action"] == action:
                return {"decision": action, "reason": "matched-" + rule["dimension"],
                        "rule_id": rule["rule_id"]}
    if get_mode(conn, recipient) == "allowlist" and not any(
            rule["action"] == "allow" for rule in matches):
        # Hold unmatched traffic locally rather than implying a sender refusal.
        return {"decision": "mute", "reason": "not-allowlisted", "rule_id": None}
    return {"decision": "pass", "reason": "allowed-by-rule" if any(
        rule["action"] == "allow" for rule in matches) else "open-default",
        "rule_id": next((rule["rule_id"] for rule in matches
                         if rule["action"] == "allow"), None)}


def receive(conn, recipient, *, source_id, channel, sender_id, body,
            sender_verified=False, topics=(), topics_trusted=False,
            sender_display=None, now_ns=None):
    """Admit one transport-observed item, or suppress it without content logging.

    source_id must come from a transport adapter, never just the body. No
    read receipt, transport success, rejection or reply is inferred here.
    """
    recipient = _owner(recipient)
    source_id = _string(source_id, 250)
    sender_id = _string(sender_id, 250)
    if channel not in CHANNELS:
        raise ValueError("unsupported channel")
    if not isinstance(body, str) or not body.strip() or len(body) > 12000:
        raise ValueError("invalid message body")
    if sender_display is None:
        sender_display = sender_id
    sender_display = _string(sender_display, 250)
    now = time.time_ns() if now_ns is None else now_ns
    if type(now) is not int or now <= 0:
        raise ValueError("invalid event time")
    verdict = decide(conn, recipient, sender_id=sender_id,
                     sender_verified=sender_verified, topics=topics,
                     topics_trusted=topics_trusted, body=body)
    # A transport ID is scoped to its sender. Reusing an ID cannot
    # suppress a different participant's message.
    digest = _digest(sender_id + "\x00" + source_id)
    with conn:
        prior = conn.execute(
            "SELECT decision FROM attention_decisions "
            "WHERE recipient=? AND channel=? AND source_digest=?",
            (recipient, channel, digest)).fetchone()
        if prior:
            return {"status": "duplicate", "original_decision": prior[0]}
        decision_id = uuid4().hex
        conn.execute(
            "INSERT INTO attention_decisions "
            "(decision_id,recipient,channel,source_digest,sender_digest,"
            "sender_verified,decision,reason,occurred_ns) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (decision_id, recipient, channel, digest, _digest(sender_id),
             int(sender_verified), verdict["decision"], verdict["reason"], now))
        if verdict["decision"] != "block":
            conn.execute(
                "INSERT INTO attention_inbox "
                "(decision_id,recipient,channel,sender_display,body,state,expires_ns) "
                "VALUES (?,?,?,?,?,?,?)",
                (decision_id, recipient, channel, sender_display, body,
                 "muted" if verdict["decision"] == "mute" else "visible",
                 now + (MUTED_TTL_NS if verdict["decision"] == "mute"
                        else VISIBLE_TTL_NS)))
    return {"status": "filtered", "decision_id": decision_id, **verdict}


def list_inbox(conn, recipient, *, include_muted=False, limit=50):
    recipient = _owner(recipient)
    if type(include_muted) is not bool or type(limit) is not int or not 1 <= limit <= 200:
        raise ValueError("invalid inbox query")
    rows = conn.execute(
        "SELECT decision_id,channel,sender_display,body,state,expires_ns "
        "FROM attention_inbox WHERE recipient=? "
        + ("" if include_muted else "AND state='visible' ")
        + "ORDER BY expires_ns DESC LIMIT ?", (recipient, limit)).fetchall()
    return [dict(zip(("decision_id","channel","sender_display","body",
                       "state","expires_ns"), row)) for row in rows]


def recent_audit(conn, recipient, limit=50):
    if type(limit) is not int or not 1 <= limit <= 200:
        raise ValueError("invalid audit limit")
    rows = conn.execute(
        "SELECT occurred_ns,channel,decision,reason,sender_verified "
        "FROM attention_decisions WHERE recipient=? "
        "ORDER BY occurred_ns DESC LIMIT ?", (_owner(recipient), limit)).fetchall()
    return [dict(zip(("occurred_ns","channel","decision","reason",
                      "sender_verified"), r)) for r in rows]


def prune(conn, *, now_ns=None):
    """Expire message bodies quickly, audit after 30d, replay cache after 90d."""
    now = time.time_ns() if now_ns is None else now_ns
    if type(now) is not int or now <= 0:
        raise ValueError("invalid prune time")
    with conn:
        bodies = conn.execute(
            "DELETE FROM attention_inbox WHERE expires_ns<=?", (now,)).rowcount
        audit = conn.execute(
            "UPDATE attention_decisions SET reason='expired-audit' "
            "WHERE occurred_ns<=? AND reason!='expired-audit'",
            (now - AUDIT_TTL_NS,)).rowcount
        replay = conn.execute(
            "DELETE FROM attention_decisions WHERE occurred_ns<=?",
            (now - REPLAY_TTL_NS,)).rowcount
    return {"expired_bodies": bodies, "expired_audit_details": audit,
            "expired_replay_records": replay}
