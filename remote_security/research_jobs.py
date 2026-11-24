"""B5/B2 read-only, allowlisted research-data checks with durable HMAC receipts.

No arbitrary shell, executable, project path, network, UI, or source-file access.
The only input is bounded caller-provided bytes; the only persistent side effect
is a private SQLite receipt. This is NOT an independent scientific measurement.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
import hashlib
import hmac
import json
import os
import re
import sqlite3
import stat
import sys

from remote_security.private_store import connect_private, _validate_path

VERSION = 1
MAX_INPUT = 65536
_ID = re.compile(r"[A-Za-z0-9_-]{8,64}\Z")
_PROJECT = re.compile(r"[A-Za-z0-9_-]{2,64}\Z")
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_COMMANDS = frozenset({"sha256-echo", "json-object-check", "utf8-line-count"})


class JobRejected(ValueError):
    """No job was reserved: invalid policy, request, or replay."""


class JobUncertain(RuntimeError):
    """A job may have started; do not retry with this ID."""


class UntrustedReceipt(ValueError):
    """Stored receipt fails integrity checks."""


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def _valid_id(value):
    return type(value) is str and _ID.fullmatch(value) is not None


def _valid_project(value):
    return type(value) is str and _PROJECT.fullmatch(value) is not None


def _unique_pairs(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError("duplicate JSON key")
        out[key] = value
    return out


def _reject_constant(value):
    raise ValueError("nonfinite JSON constant")


def _run_builtin(command, payload):
    if command == "sha256-echo":
        return 0, {"sha256": hashlib.sha256(payload).hexdigest(), "bytes": len(payload)}
    try:
        decoded = payload.decode("utf-8")
    except UnicodeError:
        return 2, {"error": "invalid_utf8"}
    if command == "utf8-line-count":
        return 0, {"lines": decoded.count("\n") + int(bool(decoded) and not decoded.endswith("\n")),
                   "bytes": len(payload)}
    if command == "json-object-check":
        try:
            value = json.loads(decoded, object_pairs_hook=_unique_pairs,
                               parse_constant=_reject_constant)
            if type(value) is not dict:
                raise ValueError("not an object")
            stack = [(value, 0)]
            while stack:
                item, depth = stack.pop()
                if depth > 64:
                    raise ValueError("excessive nesting")
                if type(item) is dict:
                    stack.extend((v, depth + 1) for v in item.values())
                elif type(item) is list:
                    stack.extend((v, depth + 1) for v in item)
            return 0, {"valid": True, "top_level_fields": len(value)}
        except (ValueError, RecursionError):
            return 2, {"error": "invalid_json_object"}
    raise JobRejected("command not built in")


class ResearchJobs:
    def __init__(self, database, receipt_key, allowlist, clock=None, audit_only=False):
        if type(receipt_key) is not bytes or len(receipt_key) < 32:
            raise JobRejected("private receipt key must contain at least 32 bytes")
        if type(allowlist) is not dict or not allowlist:
            raise JobRejected("nonempty explicit project allowlist required")
        normalized = {}
        for project, commands in allowlist.items():
            if not _valid_project(project) or type(commands) not in (list, tuple, set, frozenset):
                raise JobRejected("invalid project policy")
            if not commands or any(type(x) is not str or x not in _COMMANDS for x in commands):
                raise JobRejected("unknown or empty command policy")
            normalized[project] = sorted(set(commands))
        self.allowlist = normalized
        self.policy_sha256 = hashlib.sha256(canonical(normalized)).hexdigest()
        # Source-file hash is a provenance pointer, NOT loaded-code attestation.
        self.adapter_source_sha256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        self.database = str(database)
        self.key = receipt_key
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.audit_only = audit_only
        if not audit_only:
            db = connect_private(self.database)
            try:
                db.execute("""CREATE TABLE IF NOT EXISTS research_jobs (
                    project TEXT NOT NULL, job_id TEXT NOT NULL, command TEXT NOT NULL,
                    input_sha TEXT NOT NULL, state TEXT NOT NULL,
                    receipt BLOB, output BLOB, mac TEXT,
                    PRIMARY KEY(project, job_id))""")
            finally:
                db.close()

    def _stamp(self):
        value = self.clock()
        if not isinstance(value, datetime) or value.tzinfo is None:
            raise JobRejected("aware clock required")
        return value.astimezone(timezone.utc).isoformat(timespec="microseconds")

    def run_once(self, request, payload):
        if self.audit_only:
            raise JobRejected("audit-only instance cannot execute")
        if type(request) is not dict or set(request) != {"project", "job_id", "command", "input_sha256"}:
            raise JobRejected("exact request schema required")
        project, job_id, command, digest = (request[k] for k in
                                             ("project", "job_id", "command", "input_sha256"))
        if not _valid_project(project) or not _valid_id(job_id):
            raise JobRejected("invalid identifiers")
        if type(command) is not str or command not in self.allowlist.get(project, ()):
            raise JobRejected("project/command route forbidden")
        if type(payload) is not bytes or len(payload) > MAX_INPUT:
            raise JobRejected("input must be bounded bytes")
        if type(digest) is not str or not _SHA.fullmatch(digest):
            raise JobRejected("invalid input SHA256")
        if not hmac.compare_digest(hashlib.sha256(payload).hexdigest(), digest):
            raise JobRejected("input digest mismatch")
        started = self._stamp()
        # Commit a reservation BEFORE any check. Crash => uncertain; never retry.
        db = connect_private(self.database)
        try:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM research_jobs WHERE project=? AND job_id=?",
                          (project, job_id)).fetchone():
                db.execute("ROLLBACK")
                raise JobRejected("replay or colliding job ID")
            db.execute("INSERT INTO research_jobs(project,job_id,command,input_sha,state) VALUES (?,?,?,?,?)",
                       (project, job_id, command, digest, "started_uncertain"))
            db.execute("COMMIT")
        except sqlite3.Error as exc:
            if db.in_transaction:
                db.execute("ROLLBACK")
            raise JobUncertain("reservation outcome uncertain") from exc
        finally:
            db.close()
        try:
            exit_status, output = _run_builtin(command, payload)
            output_bytes = canonical(output)
            finished = self._stamp()
            receipt = {"version": VERSION, "project": project, "job_id": job_id,
                       "command": command, "policy_sha256": self.policy_sha256,
                       "adapter_source_sha256": self.adapter_source_sha256,
                       "input_sha256": digest,
                       "output_sha256": hashlib.sha256(output_bytes).hexdigest(),
                       "started_utc": started, "finished_utc": finished,
                       "exit_status": exit_status,
                       "evidence": "local_builtin_check_not_independent_measurement"}
            receipt_bytes = canonical(receipt)
            mac = hmac.new(self.key, receipt_bytes, hashlib.sha256).hexdigest()
            db = connect_private(self.database)
            try:
                db.execute("BEGIN IMMEDIATE")
                db.execute("""UPDATE research_jobs SET state='completed',receipt=?,output=?,mac=?
                           WHERE project=? AND job_id=? AND state='started_uncertain'""",
                           (receipt_bytes, output_bytes, mac, project, job_id))
                if db.total_changes != 1:
                    raise JobUncertain("reservation changed before completion")
                db.execute("COMMIT")
            except sqlite3.Error as exc:
                if db.in_transaction:
                    db.execute("ROLLBACK")
                raise JobUncertain("completion outcome uncertain") from exc
            finally:
                db.close()
            return {"receipt": receipt, "mac": mac, "output": output}
        except Exception as exc:
            if isinstance(exc, JobUncertain):
                raise
            raise JobUncertain("job started but outcome uncertain; do not retry") from exc

    def audit(self, project, job_id):
        if not _valid_project(project) or not _valid_id(job_id):
            raise JobRejected("invalid audit identifiers")
        db = _connect_readonly(self.database)
        try:
            row = db.execute("SELECT state,receipt,output,mac,command,input_sha FROM research_jobs WHERE project=? AND job_id=?",
                             (project, job_id)).fetchone()
        finally:
            db.close()
        if row is None:
            return {"state": "not_found_not_proof_of_nonexecution"}
        state, receipt_bytes, output_bytes, mac, stored_command, stored_input_sha = row
        if state == "started_uncertain" and receipt_bytes is None and output_bytes is None and mac is None:
            return {"state": "started_uncertain_no_retry"}
        if state != "completed" or type(receipt_bytes) is not bytes or type(output_bytes) is not bytes or type(mac) is not str:
            raise UntrustedReceipt("invalid stored state")
        if not hmac.compare_digest(hmac.new(self.key, receipt_bytes, hashlib.sha256).hexdigest(), mac):
            raise UntrustedReceipt("receipt MAC mismatch")
        try:
            receipt = json.loads(receipt_bytes, object_pairs_hook=_unique_pairs)
            output = json.loads(output_bytes, object_pairs_hook=_unique_pairs)
        except (ValueError, UnicodeError) as exc:
            raise UntrustedReceipt("stored JSON malformed") from exc
        if (type(receipt) is not dict or receipt.get("project") != project
                or receipt.get("job_id") != job_id or receipt.get("policy_sha256") != self.policy_sha256
                or receipt.get("command") != stored_command
                or receipt.get("input_sha256") != stored_input_sha
                or type(receipt.get("adapter_source_sha256")) is not str
                or not _SHA.fullmatch(receipt["adapter_source_sha256"])
                or receipt.get("output_sha256") != hashlib.sha256(output_bytes).hexdigest()
                or canonical(receipt) != receipt_bytes or canonical(output) != output_bytes):
            raise UntrustedReceipt("stored output or policy mismatch")
        return {"state": "completed_local_only", "receipt": receipt, "mac": mac, "output": output}


def _connect_readonly(path):
    """Never create a database or SQLite journal during receipt reconciliation."""
    p = _validate_path(path)
    fd = os.open(p, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) |
                 getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NONBLOCK", 0))
    try:
        s = os.fstat(fd)
        if (not stat.S_ISREG(s.st_mode) or s.st_uid != os.getuid()
                or s.st_mode & 0o077 or s.st_nlink != 1):
            raise PermissionError("receipt database must be private regular file")
    finally:
        os.close(fd)
    db = sqlite3.connect("file:" + quote(str(p), safe="/") + "?mode=ro",
                         uri=True, timeout=3, isolation_level=None)
    db.execute("PRAGMA query_only=ON")
    return db


def _load_receipt_key(path):
    p = _validate_path(path)
    fd = os.open(p, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) |
                 getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NONBLOCK", 0))
    try:
        s = os.fstat(fd)
        if (not stat.S_ISREG(s.st_mode) or s.st_uid != os.getuid()
                or s.st_mode & 0o077 or s.st_nlink != 1):
            raise PermissionError("key must be private regular file")
        data = os.read(fd, 257)
        if not 32 <= len(data) <= 256:
            raise ValueError("key length must be 32..256 bytes")
        return data
    finally:
        os.close(fd)


def main(argv=None):
    parser = argparse.ArgumentParser(description="One-shot read-only research data checks; never a ChatGPT wake")
    parser.add_argument("--database", required=True)
    parser.add_argument("--receipt-key-file", required=True)
    parser.add_argument("--allow", action="append", required=True, metavar="PROJECT:COMMAND")
    parser.add_argument("--project", required=True)
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--command")
    parser.add_argument("--input-sha256")
    parser.add_argument("--audit", action="store_true", help="read existing receipt; do not execute")
    args = parser.parse_args(argv)
    try:
        allowed = {}
        for item in args.allow:
            project, sep, command = item.partition(":")
            if not sep:
                raise JobRejected("invalid allow entry")
            allowed.setdefault(project, []).append(command)
        adapter = ResearchJobs(args.database, _load_receipt_key(args.receipt_key_file),
                               allowed, audit_only=args.audit)
        if args.audit:
            result = adapter.audit(args.project, args.job_id)
        else:
            payload = sys.stdin.buffer.read(MAX_INPUT + 1)
            result = adapter.run_once({"project": args.project, "job_id": args.job_id,
                                       "command": args.command, "input_sha256": args.input_sha256}, payload)
        print(canonical(result).decode("ascii"))
        return result.get("receipt", {}).get("exit_status", 0)
    except (JobRejected, JobUncertain, UntrustedReceipt, PermissionError, OSError, ValueError) as exc:
        print(canonical({"state": "rejected_or_uncertain", "error_type": type(exc).__name__}).decode("ascii"), file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
