"""B5 experimental, NON-AUTHORIZING B1 retirement evidence quarantine.

A receipt is a claim about a UI observation, not a ChatGPT response proof.
This module never changes B1's admissions table or authorizes a UI Send.
The caller MUST derive peer_uid from SO_PEERCRED on a separate-UID broker;
JSON sender_id, process names, and file ownership are not authentication.
"""
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import sqlite3
import stat
import struct

ID = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
SHA = re.compile(r"^[0-9a-f]{64}$")
FIELDS = ("conversation_id", "message_id", "origin_turn_id", "sender_id", "payload_sha256")
SCHEMA = """
CREATE TABLE IF NOT EXISTS retirement_candidates (
 conversation_id TEXT PRIMARY KEY,
 message_id TEXT NOT NULL,
 envelope_sha256 TEXT NOT NULL,
 evidence_sha256 TEXT NOT NULL,
 observed_user_turn_id TEXT NOT NULL UNIQUE,
 observed_assistant_turn_id TEXT NOT NULL UNIQUE,
 attestor_uid INTEGER NOT NULL,
 state TEXT NOT NULL CHECK(state='quarantined_not_retired'),
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


def kernel_peer_uid(conn):
    """Read authenticated Linux AF_UNIX peer UID, never a JSON assertion."""
    if not hasattr(socket, "SO_PEERCRED") or conn.family != socket.AF_UNIX:
        raise ValueError("Linux AF_UNIX peer credentials required")
    raw = conn.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
    return struct.unpack("3i", raw)[1]


def _valid_id(value):
    return type(value) is str and bool(ID.fullmatch(value))


def _valid_sha(value):
    return type(value) is str and bool(SHA.fullmatch(value))


def _canonical_sha(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=True,
                                     separators=(",", ":")).encode("ascii")).hexdigest()


def evaluate_candidate(admission, receipt, *, peer_uid, trusted_attestor_uid, broker_uid):
    """Return a non-authorizing decision. Never returns 'retired' or 'send'.

    The broker is responsible for checking that the *current* admission row
    matches admission in the same durable transaction as any future retirement.
    A separately authenticated UID does not itself prove that the UI was read.
    """
    if any(type(v) is not int or v < 0 for v in (peer_uid, trusted_attestor_uid, broker_uid)):
        return "reject_invalid_uid"
    if trusted_attestor_uid == broker_uid or peer_uid != trusted_attestor_uid:
        return "reject_untrusted_attestor"
    if type(admission) is not dict or type(receipt) is not dict:
        return "reject_invalid_evidence"
    if set(admission) != set((*FIELDS, "state")) or set(receipt) != set((*FIELDS, "state", "observed_user_turn_id", "observed_assistant_turn_id")):
        return "reject_invalid_evidence"
    if admission.get("state") != "uncertain":
        return "reject_not_uncertain"
    if receipt.get("state") != "verified":
        return "reject_unverified_receipt"
    if any(not _valid_id(admission.get(k)) for k in FIELDS[:-1]):
        return "reject_invalid_envelope"
    if not _valid_sha(admission.get("payload_sha256")):
        return "reject_invalid_envelope"
    if any(receipt.get(k) != admission[k] or type(receipt.get(k)) is not str for k in FIELDS):
        return "reject_binding_mismatch"
    if not _valid_id(receipt.get("observed_user_turn_id")) or not _valid_id(receipt.get("observed_assistant_turn_id")):
        return "reject_missing_turn_ids"
    if receipt["observed_user_turn_id"] == receipt["observed_assistant_turn_id"]:
        return "reject_colliding_turn_ids"
    if receipt["observed_assistant_turn_id"] == admission["origin_turn_id"]:
        return "reject_reused_origin_turn"
    # Timestamp ordering is not a source of authority: never use client time
    # to prove freshness or retire a pending attempt.
    return "candidate_quarantined_not_retired"


class Quarantine:
    """Append-only durable evidence index, intentionally NOT an admission store.

    Requires an existing private, service-owned directory (mode 0700); do not
    share this directory with the browser or the attestor UID. The database is
    only for evidence deduplication. It cannot grant another wake.
    """
    def __init__(self, db_path):
        raw = os.fspath(db_path)
        if type(raw) is not str or os.path.normpath(raw) != raw:
            raise ValueError("noncanonical database path")
        self.path = Path(raw)
        if not self.path.is_absolute() or str(self.path) != raw:
            raise ValueError("absolute canonical database path required")
        parent = self.path.parent
        ancestor = Path("/")
        for part in parent.parts[1:]:
            ancestor = ancestor / part
            if ancestor.is_symlink():
                raise ValueError("symlinked evidence ancestor")
        st = parent.lstat()
        if not stat.S_ISDIR(st.st_mode) or st.st_uid != os.geteuid() or st.st_mode & 0o077:
            raise PermissionError("private service-owned evidence directory required")
        if self.path.is_symlink():
            raise ValueError("symlinked evidence database")
        if self.path.exists():
            self._check_db()
        else:
            flags = os.O_CREAT | os.O_EXCL | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
            fd = os.open(self.path, flags, 0o600)
            os.close(fd)
        self._check_db()
        with closing(self._connect()) as db:
            db.executescript(SCHEMA)

    def _check_db(self):
        st = self.path.lstat()
        if not stat.S_ISREG(st.st_mode) or st.st_uid != os.geteuid() or st.st_nlink != 1 or st.st_mode & 0o077:
            raise PermissionError("unsafe evidence database")

    def _connect(self):
        self._check_db()
        db = sqlite3.connect(str(self.path), timeout=5, isolation_level=None)
        db.execute("PRAGMA busy_timeout=5000")
        return db

    def record_from_socket(self, conn, admission, receipt, *, trusted_attestor_uid):
        """Production entry: bind attestor to Linux kernel credentials."""
        return self._record_authenticated(admission, receipt,
            peer_uid=kernel_peer_uid(conn), trusted_attestor_uid=trusted_attestor_uid,
            broker_uid=os.geteuid())

    def _record_authenticated(self, admission, receipt, *, peer_uid, trusted_attestor_uid, broker_uid):
        """Internal policy hook; direct UID injection is ONLY for isolated tests."""
        decision = evaluate_candidate(admission, receipt, peer_uid=peer_uid,
                                      trusted_attestor_uid=trusted_attestor_uid, broker_uid=broker_uid)
        if decision != "candidate_quarantined_not_retired":
            return decision
        envelope = {k: admission[k] for k in FIELDS}
        evidence = {k: receipt[k] for k in (*FIELDS, "state", "observed_user_turn_id", "observed_assistant_turn_id")}
        envelope_sha, evidence_sha = _canonical_sha(envelope), _canonical_sha(evidence)
        with closing(self._connect()) as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                old = db.execute("SELECT message_id,envelope_sha256,evidence_sha256 FROM retirement_candidates WHERE conversation_id=?",
                                 (admission["conversation_id"],)).fetchone()
                if old is not None:
                    result = "duplicate_quarantined_not_retired" if old == (admission["message_id"], envelope_sha, evidence_sha) else "conflict_quarantined_not_retired"
                else:
                    try:
                        db.execute("INSERT INTO retirement_candidates(conversation_id,message_id,envelope_sha256,evidence_sha256,observed_user_turn_id,observed_assistant_turn_id,attestor_uid,state) VALUES(?,?,?,?,?,?,?,'quarantined_not_retired')",
                                   (admission["conversation_id"], admission["message_id"], envelope_sha, evidence_sha, receipt["observed_user_turn_id"], receipt["observed_assistant_turn_id"], peer_uid))
                        result = "candidate_quarantined_not_retired"
                    except sqlite3.IntegrityError:
                        result = "cross_target_turn_reuse_quarantined"
                db.execute("COMMIT")
                return result
            except BaseException:
                db.execute("ROLLBACK")
                raise

    def status(self, conversation_id):
        if not _valid_id(conversation_id):
            raise ValueError("invalid conversation id")
        with closing(self._connect()) as db:
            row = db.execute("SELECT message_id,evidence_sha256,state FROM retirement_candidates WHERE conversation_id=?",
                             (conversation_id,)).fetchone()
        return None if row is None else {"message_id": row[0], "evidence_sha256": row[1], "state": row[2]}
