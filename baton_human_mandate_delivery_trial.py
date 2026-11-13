"""Isolated composition of human approval, possible click, lost receipt, and revoke.

A fake external send can lose its acknowledgement after it may have committed.
A durable pre-effect journal fences blind retries; subsequent revocation cannot
rewrite a possibly delivered action as canceled. No browser, ChatGPT, portal
or production database is accessed. A real physical commit boundary is NOT
provided or proven by this model.
"""
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
from pathlib import Path
import sqlite3
from threading import RLock


@dataclass(frozen=True)
class Approval:
    session: str
    target: str
    operation: str
    content_sha256: str
    generation: int


class ApprovalStore:
    def __init__(self):
        self.lock = RLock()
        self.generation = 1
        self.active = True
        self.session = "session-A"

    def approve(self, target, content, operation="send"):
        with self.lock:
            return Approval(self.session, target, operation,
                            hashlib.sha256(content.encode()).hexdigest(),
                            self.generation)

    def revoke(self):
        with self.lock:
            self.generation += 1
            self.active = False

    def valid(self, proof, target, content):
        return (self.active and proof.session == self.session
                and proof.generation == self.generation
                and proof.target == target
                and proof.operation == "send"
                and proof.content_sha256 == hashlib.sha256(content.encode()).hexdigest())


class Journal:
    STATES = {"may_have_sent", "canceled_before_effect",
              "click_returned_unconfirmed", "delivery_uncertain",
              "source_reply_observed"}

    def __init__(self, path):
        self.path = Path(path)
        with self.db() as c:
            c.execute("""CREATE TABLE IF NOT EXISTS attempts(
                intent_id TEXT PRIMARY KEY, target TEXT NOT NULL,
                digest TEXT NOT NULL, state TEXT NOT NULL, receipt TEXT)""")

    @contextmanager
    def db(self):
        c = sqlite3.connect(self.path)
        c.row_factory = sqlite3.Row
        try:
            with c:
                yield c
        finally:
            c.close()

    def get(self, intent):
        with self.db() as c:
            row = c.execute("SELECT * FROM attempts WHERE intent_id=?",
                            (intent,)).fetchone()
        return dict(row) if row else None

    def begin(self, intent, approval, target, content, store):
        digest = hashlib.sha256(content.encode()).hexdigest()
        with store.lock:
            with self.db() as c:
                c.execute("BEGIN IMMEDIATE")
                if c.execute("SELECT 1 FROM attempts WHERE intent_id=?",
                             (intent,)).fetchone():
                    return False
                allowed = store.valid(approval, target, content)
                state = "may_have_sent" if allowed else "canceled_before_effect"
                c.execute("INSERT INTO attempts VALUES (?,?,?,?,NULL)",
                          (intent, target, digest, state))
                return allowed

    def transition(self, intent, new_state, receipt=None):
        if new_state not in self.STATES:
            raise ValueError("unknown state")
        with self.db() as c:
            row = c.execute("SELECT state FROM attempts WHERE intent_id=?",
                            (intent,)).fetchone()
            if row is None:
                raise ValueError("unknown intent")
            prior = row["state"]
            legal = {
                "may_have_sent": {"click_returned_unconfirmed", "delivery_uncertain",
                                  "source_reply_observed"},
                "click_returned_unconfirmed": {"delivery_uncertain",
                                               "source_reply_observed"},
                "delivery_uncertain": {"source_reply_observed"},
                "canceled_before_effect": set(),
                "source_reply_observed": set()
            }
            if new_state not in legal[prior]:
                raise ValueError(f"unsafe journal rewrite: {prior} -> {new_state}")
            c.execute("UPDATE attempts SET state=?,receipt=? WHERE intent_id=?",
                      (new_state, receipt, intent))

    def observe(self, intent, *, new_message_id, exact_target, exact_digest,
                source_bound, after_baseline, actual_reply_id):
        row = self.get(intent)
        if (row is None or row["state"] == "canceled_before_effect" or
            not source_bound or not after_baseline or not new_message_id or
            not actual_reply_id or exact_target != row["target"] or
            exact_digest != row["digest"]):
            return False
        self.transition(intent, "source_reply_observed", actual_reply_id)
        return True


def attempt_send(journal, store, intent, proof, target, content, fake_send):
    # Journal must precede any external effect because an exception from
    # fake_send could occur AFTER a physical commit in a real adapter.
    if not journal.begin(intent, proof, target, content, store):
        return False
    try:
        fake_send(target, content)
        journal.transition(intent, "click_returned_unconfirmed")
    except Exception:
        journal.transition(intent, "delivery_uncertain")
    return True
