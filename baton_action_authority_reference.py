"""Experimental SQLite authority fence for cross-conversation Baton actions.

REFERENCE IMPLEMENTATION ONLY. It is intentionally not connected to the
production UI sender, and does NOT authenticate owner names, authorize
ChatGPT account access or make remote side effects atomic.

Motivation: 2026-11-12 real sequential conversations with Spire, Siv, Vev,
and Lodd. A new message_id must not resurrect an action whose original
grant was revoked. Keep evidence of effect attempts separate from authority.
"""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import re
import sqlite3


IDENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")
STATES = ("pending", "challenged", "reserved", "revoked",
          "effect_unknown", "effect_confirmed")


def _id(value):
    if not isinstance(value, str) or not IDENT.fullmatch(value):
        raise ValueError("invalid stable identifier")
    return value


class ActionFence:
    """A SQLite reference for one action/grant identity across all workers.

    Trust boundary: caller identities and grant authenticity MUST already
    have been verified by an external authenticated authorization layer.
    Merely passing owner='Lodd' is not proof of Lodd's authority.
    """

    def __init__(self, db_path):
        self.path = Path(db_path)
        if self.path.is_symlink():
            raise ValueError("symlinked database denied")

    @contextmanager
    def _connection(self):
        conn = sqlite3.connect(str(self.path), timeout=5,
                               isolation_level=None)
        conn.execute("PRAGMA busy_timeout=5000")
        try:
            yield conn
        finally:
            conn.close()

    def init(self):
        with self._connection() as c:
            c.execute("PRAGMA journal_mode=WAL")
            c.execute("PRAGMA synchronous=FULL")
            c.executescript("""
                CREATE TABLE IF NOT EXISTS actions(
                    action_id TEXT PRIMARY KEY,
                    grant_id TEXT NOT NULL UNIQUE,
                    owner_id TEXT NOT NULL,
                    recipient_id TEXT NOT NULL,
                    effect_key TEXT NOT NULL,
                    origin_message_id TEXT NOT NULL,
                    revision INTEGER NOT NULL CHECK (revision>=1),
                    state TEXT NOT NULL CHECK (state IN (
                       'pending','challenged','reserved','revoked',
                       'effect_unknown','effect_confirmed')),
                    lease_token TEXT
                );
                CREATE TABLE IF NOT EXISTS tombstones(
                    grant_id TEXT PRIMARY KEY,
                    action_id TEXT NOT NULL,
                    revoked_revision INTEGER NOT NULL,
                    UNIQUE(action_id, grant_id)
                );
                CREATE TABLE IF NOT EXISTS challenges(
                    challenge_id TEXT PRIMARY KEY,
                    action_id TEXT NOT NULL,
                    challenger_id TEXT NOT NULL,
                    note TEXT NOT NULL,
                    resolved INTEGER NOT NULL DEFAULT 0
                );
            """)

    def create(self, *, action_id, grant_id, owner_id, recipient_id,
               effect_key, origin_message_id):
        vals = [_id(x) for x in (action_id, grant_id, owner_id,
                recipient_id, effect_key, origin_message_id)]
        with self._connection() as c:
            c.execute("BEGIN IMMEDIATE")
            if c.execute("SELECT 1 FROM tombstones WHERE grant_id=?",
                         (grant_id,)).fetchone():
                c.rollback()
                return False
            # Both action ID and grant ID are stable across conversation IDs
            # and new message IDs. No text-equivalence guessing is involved.
            try:
                c.execute("""INSERT INTO actions
                    (action_id,grant_id,owner_id,recipient_id,effect_key,
                     origin_message_id,revision,state,lease_token)
                     VALUES(?,?,?,?,?,?,1,'pending',NULL)""", vals)
            except sqlite3.IntegrityError:
                c.rollback()
                return False
            c.commit()
            return True

    def reserve(self, *, action_id, grant_id, lease_token,
                actor_id, requested_effect_key):
        """Scope actor and operation before a worker can reserve.

        actor_id must be supplied by VERIFIED transport identity, not copied
        from the user's message. This reference does not perform authn.
        """
        for value in (action_id, grant_id, lease_token, actor_id,
                      requested_effect_key):
            _id(value)
        with self._connection() as c:
            c.execute("BEGIN IMMEDIATE")
            changed = c.execute("""UPDATE actions
                SET state='reserved', lease_token=?
                WHERE action_id=? AND grant_id=? AND state='pending'
                  AND recipient_id=? AND effect_key=?
                  AND NOT EXISTS(
                    SELECT 1 FROM tombstones WHERE grant_id=?
                  )""", (lease_token, action_id, grant_id,
                         actor_id, requested_effect_key, grant_id)).rowcount
            c.commit()
            return changed == 1

    def challenge(self, *, action_id, challenge_id, challenger_id, note):
        _id(action_id); _id(challenge_id); _id(challenger_id)
        if not isinstance(note, str) or not 1 <= len(note) <= 500:
            raise ValueError("invalid challenge note")
        with self._connection() as c:
            c.execute("BEGIN IMMEDIATE")
            row = c.execute("SELECT state FROM actions WHERE action_id=?",
                            (action_id,)).fetchone()
            if not row or row[0] not in ("pending", "reserved"):
                c.rollback()
                return False
            try:
                c.execute("""INSERT INTO challenges
                    (challenge_id,action_id,challenger_id,note)
                    VALUES(?,?,?,?)""",
                    (challenge_id, action_id, challenger_id, note))
            except sqlite3.IntegrityError:
                c.rollback()
                return False
            # Challenge is NOT revocation: pause exactly this action and
            # invalidate its lease until the verified owner resolves it.
            c.execute("""UPDATE actions SET state='challenged',lease_token=NULL
                         WHERE action_id=?""", (action_id,))
            c.commit()
            return True

    def dismiss_challenge(self, *, action_id, actor_id):
        _id(action_id); _id(actor_id)
        with self._connection() as c:
            c.execute("BEGIN IMMEDIATE")
            row = c.execute("SELECT owner_id,state FROM actions WHERE action_id=?",
                            (action_id,)).fetchone()
            if not row or row[0] != actor_id:
                c.rollback()
                raise PermissionError("only authenticated owner can resolve")
            if row[1] != "challenged":
                c.rollback()
                return False
            c.execute("""UPDATE actions SET state='pending',lease_token=NULL
                         WHERE action_id=?""", (action_id,))
            c.execute("""UPDATE challenges SET resolved=1
                         WHERE action_id=? AND resolved=0""", (action_id,))
            c.commit()
            return True

    def revoke(self, *, action_id, actor_id):
        _id(action_id); _id(actor_id)
        with self._connection() as c:
            c.execute("BEGIN IMMEDIATE")
            row = c.execute("""SELECT grant_id,owner_id,state,revision
                               FROM actions WHERE action_id=?""",
                            (action_id,)).fetchone()
            if not row or row[1] != actor_id:
                c.rollback()
                raise PermissionError("only authenticated owner can revoke")
            grant_id, _, old_state, old_rev = row
            if old_state == "revoked":
                c.rollback()
                return False
            new_rev = old_rev + 1
            # If the external effect may already have started, never claim
            # it did not happen: effect_unknown is deliberately sticky.
            new_state = ("effect_unknown"
                         if old_state in ("effect_unknown","effect_confirmed")
                         else "revoked")
            c.execute("""UPDATE actions
                         SET revision=?,state=?,lease_token=NULL
                         WHERE action_id=?""",
                      (new_rev, new_state, action_id))
            c.execute("""INSERT OR IGNORE INTO tombstones
                         (grant_id,action_id,revoked_revision)
                         VALUES(?,?,?)""", (grant_id,action_id,new_rev))
            c.commit()
            return True

    def begin_effect(self, *, action_id, grant_id,
                     reserved_revision, lease_token, actor_id,
                     requested_effect_key):
        """Atomic last *local* fence, not an atomic remote send.

        A true result MUST be treated as effect outcome UNKNOWN until an
        independently correlated receipt arrives. Never blind-retry it.
        """
        for value in (action_id, grant_id, lease_token, actor_id,
                      requested_effect_key):
            _id(value)
        if not isinstance(reserved_revision, int) or reserved_revision < 1:
            raise ValueError("invalid revision")
        with self._connection() as c:
            c.execute("BEGIN IMMEDIATE")
            changed = c.execute("""UPDATE actions
                SET state='effect_unknown', lease_token=NULL
                WHERE action_id=? AND grant_id=? AND revision=?
                  AND lease_token=? AND state='reserved'
                  AND recipient_id=? AND effect_key=?
                  AND NOT EXISTS(
                    SELECT 1 FROM tombstones WHERE grant_id=?
                  )""", (action_id,grant_id,reserved_revision,lease_token,
                         actor_id,requested_effect_key,grant_id)).rowcount
            c.commit()
            return changed == 1

    def status(self, action_id):
        _id(action_id)
        with self._connection() as c:
            row = c.execute("""SELECT grant_id,revision,state,lease_token
                               FROM actions WHERE action_id=?""",
                            (action_id,)).fetchone()
            return (tuple(row) if row else None)

    def tombstoned(self, grant_id):
        _id(grant_id)
        with self._connection() as c:
            return c.execute("SELECT 1 FROM tombstones WHERE grant_id=?",
                             (grant_id,)).fetchone() is not None
