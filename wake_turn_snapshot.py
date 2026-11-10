"""B1 read-only assistant-turn snapshot for existing-chat two-hop authorization.

The stored hash is evidence of what a local DOM driver read, NOT proof of
ChatGPT authorship or an immutable server-side turn. No UI or broker writes.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib

from chatgpt_ui_driver import conversation_id
from wake_chain import next_target_from_reply

EXTRACTOR = "driver_read_assistant_turn_utf8_v1"


class SourceEvidenceChanged(RuntimeError):
    """The B turn can no longer authorize a new C click."""


@dataclass(frozen=True)
class TurnSnapshot:
    message_id: str
    chat: str
    turn_id: str
    text_sha256: str
    source_url: str
    extractor: str
    observed_utc: str


class TurnSnapshotStore:
    """Immutable first-observation record in the existing wake SQLite file."""

    def __init__(self, ledger):
        self.ledger = ledger
        with ledger.db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS wake_turn_snapshots (
                message_id TEXT PRIMARY KEY,
                chat TEXT NOT NULL,
                turn_id TEXT NOT NULL,
                text_sha256 TEXT NOT NULL,
                source_url TEXT NOT NULL,
                extractor TEXT NOT NULL,
                observed_utc TEXT NOT NULL)""")

    def get(self, message_id):
        with self.ledger.db() as db:
            row = db.execute("""SELECT message_id,chat,turn_id,text_sha256,
                source_url,extractor,observed_utc FROM wake_turn_snapshots
                WHERE message_id=?""", (message_id,)).fetchone()
        return TurnSnapshot(*row) if row else None

    def record(self, message_id, chat, turn_id, text, url):
        if not all(type(x) is str and x for x in (message_id, chat, turn_id, text, url)):
            raise SourceEvidenceChanged("Missing source-turn observation field")
        if conversation_id(url) != chat:
            raise SourceEvidenceChanged("Source URL does not match observed chat")
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        stamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        candidate = TurnSnapshot(message_id, chat, turn_id, digest, url, EXTRACTOR, stamp)
        with self.ledger.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT target,state FROM wakes WHERE id=?",
                             (message_id,)).fetchone()
            if row is None or row[0] != chat or row[1] not in ("submitting", "uncertain", "verified"):
                raise SourceEvidenceChanged("No matching reserved first-hop wake")
            old = db.execute("""SELECT message_id,chat,turn_id,text_sha256,
                source_url,extractor,observed_utc FROM wake_turn_snapshots
                WHERE message_id=?""", (message_id,)).fetchone()
            if old:
                if old[:6] != (candidate.message_id, candidate.chat, candidate.turn_id,
                               candidate.text_sha256, candidate.source_url, candidate.extractor):
                    raise SourceEvidenceChanged("First-observed B text changed; no overwrite")
                return TurnSnapshot(*old)
            db.execute("""INSERT INTO wake_turn_snapshots
                (message_id,chat,turn_id,text_sha256,source_url,extractor,observed_utc)
                VALUES (?,?,?,?,?,?,?)""",
                (candidate.message_id, candidate.chat, candidate.turn_id,
                 candidate.text_sha256, candidate.source_url, candidate.extractor,
                 candidate.observed_utc))
        return candidate


class CapturingTarget:
    """Record B's exact observed text before wake_once marks B verified."""

    def __init__(self, driver, store, message_id):
        self.driver, self.store, self.message_id = driver, store, message_id

    def __getattr__(self, name):
        return getattr(self.driver, name)

    def observe_reply(self, chat, message_id, expected_digest):
        observation = self.driver.observe_reply(chat, message_id, expected_digest)
        if observation is None:
            return None
        if message_id != self.message_id or observation.conversation_id != chat:
            raise SourceEvidenceChanged("Observed reply belongs to another wake/chat")
        if self.driver.is_generating(chat):
            return None
        text = self.driver.read_assistant_turn(chat, observation.assistant_turn_id)
        url = self.driver.page.url
        if (observation.source_url != url or
                hashlib.sha256(text.encode("utf-8")).hexdigest()
                != observation.assistant_text_sha256):
            raise SourceEvidenceChanged("B turn mutated between observation and snapshot")
        self.store.record(message_id, chat, observation.assistant_turn_id, text, url)
        return observation


def verify_current_b_turn(ledger, store, driver, first_id, chat, target):
    """Check the immutable first observation against the current B DOM turn."""
    snap = store.get(first_id)
    row = ledger.provenance(first_id)
    if (snap is None or row is None or row[1] != chat or row[4] != "verified"
            or row[5] != snap.turn_id or snap.chat != chat or snap.extractor != EXTRACTOR):
        raise SourceEvidenceChanged("Verified first-hop source snapshot missing/mismatched")
    if driver.is_generating(chat):
        raise SourceEvidenceChanged("B is generating; no C authorization")
    if driver.page.url != snap.source_url or conversation_id(driver.page.url) != chat:
        raise SourceEvidenceChanged("B source URL changed")
    text = driver.read_assistant_turn(chat, snap.turn_id)
    if hashlib.sha256(text.encode("utf-8")).hexdigest() != snap.text_sha256:
        raise SourceEvidenceChanged("B source text changed at same turn ID")
    if next_target_from_reply(text, target) is None:
        raise SourceEvidenceChanged("B did not authorize exact C target")
    return snap


def guarded_second_hop(broker_request, ledger, store, driver_b, first_id, b, c):
    """Read B before AND after each broker operation, including begin_click.

    After a committed begin_click, failure is uncertain; the outer wake
    adapter will never automatically retry the C message.
    """
    def request(envelope):
        verify_current_b_turn(ledger, store, driver_b, first_id, b, c)
        result = broker_request(envelope)
        verify_current_b_turn(ledger, store, driver_b, first_id, b, c)
        return result
    return request
