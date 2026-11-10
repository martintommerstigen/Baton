"""B5/B2 fixed-ID, read-only RustWorld source RPC over a local Unix socket.

Only an explicitly authorized *different* non-root UID may request a fixed
source ID. Never exposes arbitrary paths, commands, raw source or UI writes.
This is local byte provenance, not Greg, physics, or ChatGPT attestation.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import signal
import socket
import stat
import struct
import time

MAX_REQUEST = 4096
# A per-recv timeout alone permits an authorized slow sender to monopolize
# this single-threaded broker indefinitely by sending one byte at a time.
READ_DEADLINE_SECONDS = 3.0
ID = re.compile(r"[A-Za-z0-9_-]{8,64}\Z")


class Rejected(ValueError):
    pass


def _pairs_unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise Rejected("duplicate JSON key")
        result[key] = value
    return result


def _reject_constant(_):
    raise Rejected("nonfinite JSON")


def parse_request(raw, source_ids):
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_REQUEST or not raw.endswith(b"\n") or raw.count(b"\n") != 1:
        raise Rejected("invalid request frame")
    try:
        value = json.loads(raw[:-1].decode("utf-8"), object_pairs_hook=_pairs_unique,
                           parse_constant=_reject_constant)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise Rejected("invalid JSON") from exc
    if (type(value) is not dict or set(value) != {"version", "action", "source_id", "job_id"}
            or type(value["version"]) is not int or value["version"] != 1
            or value["action"] not in ("capture", "audit")
            or type(value["source_id"]) is not str or value["source_id"] not in source_ids
            or type(value["job_id"]) is not str or not ID.fullmatch(value["job_id"])):
        raise Rejected("request outside fixed source policy")
    return value


def _checked_parent(path):
    """No symlink ancestors; final socket parent owned by service, group-x only."""
    raw = os.fspath(path)
    if type(raw) is not str or not raw.startswith("/") or any(x in ("", ".", "..") for x in raw.split("/")[1:]):
        raise Rejected("noncanonical socket path")
    p = Path(raw)
    if p.name in ("", ".", ".."):
        raise Rejected("socket basename required")
    current = Path("/")
    for part in p.parent.parts[1:]:
        current = current / part
        s = current.lstat()
        if not stat.S_ISDIR(s.st_mode) or (s.st_mode & 0o022 and not (s.st_uid == 0 and s.st_mode & stat.S_ISVTX)):
            raise Rejected("unsafe socket ancestor")
    s = p.parent.lstat()
    if s.st_uid != os.geteuid() or s.st_mode & 0o027 or not s.st_mode & stat.S_IXGRP:
        raise Rejected("socket parent must be service-owned, non-world-accessible, group-traversable")
    return p


class SourceBroker:
    """Single-threaded, bounded, one-request-per-connection source broker."""

    def __init__(self, socket_path, allowed_uids, source_ids, capture, audit):
        if os.name != "posix" or not hasattr(socket, "SO_PEERCRED") or os.geteuid() == 0:
            raise Rejected("dedicated non-root Linux UID required")
        if (type(allowed_uids) not in (set, frozenset) or not allowed_uids
                or any(type(u) is not int or u <= 0 or u == os.geteuid() for u in allowed_uids)):
            raise Rejected("explicit different non-root caller UIDs required")
        if type(source_ids) not in (set, frozenset) or not source_ids:
            raise Rejected("fixed source IDs required")
        self.path = _checked_parent(socket_path)
        self.allowed_uids = frozenset(allowed_uids)
        self.source_ids = frozenset(source_ids)
        self.capture = capture
        self.audit = audit
        self.sock = None
        self.inode = None

    def start(self):
        if self.path.exists() or self.path.is_symlink():
            raise Rejected("socket exists; never unlink or replace an uncertain endpoint")
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            old_umask = os.umask(0o117)
            try:
                sock.bind(str(self.path))
            finally:
                os.umask(old_umask)
            os.chmod(self.path, 0o660)
            st = self.path.lstat()
            if not stat.S_ISSOCK(st.st_mode) or st.st_uid != os.geteuid() or st.st_mode & 0o007:
                raise Rejected("unsafe bound socket")
            sock.listen(4)
            sock.settimeout(1.0)
            self.inode = (st.st_dev, st.st_ino)
            self.sock = sock
        except BaseException:
            sock.close()
            raise

    def _peer_uid(self, conn):
        creds = conn.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
        if len(creds) != struct.calcsize("3i"):
            raise Rejected("missing peer credentials")
        pid, uid, _gid = struct.unpack("3i", creds)
        if pid <= 0:
            raise Rejected("invalid peer PID")
        return uid

    def _handle(self, conn):
        if self.sock is None:
            raise Rejected("not started")
        conn.settimeout(3.0)
        if self._peer_uid(conn) not in self.allowed_uids:
            return  # reject BEFORE reading any request bytes
        raw = bytearray()
        deadline = time.monotonic() + READ_DEADLINE_SECONDS
        while len(raw) <= MAX_REQUEST:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise Rejected("absolute request deadline exceeded")
            conn.settimeout(remaining)
            part = conn.recv(min(1024, MAX_REQUEST + 1 - len(raw)))
            if not part:
                break
            raw.extend(part)
        try:
            request = parse_request(bytes(raw), self.source_ids)
            if request["action"] == "capture":
                result = self.capture(request["source_id"], request["job_id"])
            else:
                result = self.audit(request["source_id"], request["job_id"])
            if type(result) is not dict or type(result.get("state")) is not str:
                raise Rejected("backend contract failure")
            reply = result
        except Exception:
            # Even a post-reservation failure may have executed. Never retry.
            reply = {"state": "rejected_or_uncertain_no_retry"}
        encoded = (json.dumps(reply, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()
        if len(encoded) > MAX_REQUEST:
            encoded = b'{"state":"rejected_or_uncertain_no_retry"}\n'
        conn.sendall(encoded)

    def accept_once(self):
        conn, _ = self.sock.accept()
        with conn:
            try:
                self._handle(conn)
            except (OSError, TimeoutError, Rejected):
                pass  # delivery uncertain; no retry

    def close(self):
        if self.sock is not None:
            self.sock.close()
            self.sock = None
        try:
            st = self.path.lstat()
            if stat.S_ISSOCK(st.st_mode) and (st.st_dev, st.st_ino) == self.inode:
                self.path.unlink()
        except FileNotFoundError:
            pass


def main(argv=None):
    from remote_security.pinned_source import capture_pinned_source
    from remote_security.pinned_source_bundle import save_pinned_bundle, load_pinned_bundle
    from remote_security.pinned_source_cli import PINNED_POLICY
    from remote_security.research_jobs import ResearchJobs, _load_receipt_key
    from remote_security.private_store import _validate_path

    p = argparse.ArgumentParser(description="Fixed-ID RustWorld read-only local broker; no TCP, shell or UI")
    for name in ("socket", "database", "receipt-key-file", "evidence-dir", "source-root"):
        p.add_argument("--" + name, required=True)
    p.add_argument("--allowed-uid", type=int, action="append", required=True)
    args = p.parse_args(argv)
    if os.geteuid() == 0:
        p.error("root is forbidden")
    evidence_dir = Path(args.evidence_dir)
    _validate_path(evidence_dir / "evidence-check.json")
    jobs = ResearchJobs(args.database, _load_receipt_key(args.receipt_key_file),
                        {"RustWorld": ["sha256-echo"]})

    def evidence_path(job_id):
        if not ID.fullmatch(job_id):
            raise Rejected("invalid job ID")
        return evidence_dir / (job_id + ".json")

    def capture(source_id, job_id):
        bundle = capture_pinned_source(jobs, args.source_root, PINNED_POLICY, source_id, job_id)
        saved = save_pinned_bundle(jobs, PINNED_POLICY, bundle, evidence_path(job_id))
        return {"state": "completed_local_pinned_source", "source_id": source_id,
                "job_id": job_id, "source_sha256": bundle["capture"]["content_sha256"],
                "evidence_sha256": saved["sha256"]}

    def audit(source_id, job_id):
        checked = load_pinned_bundle(jobs, PINNED_POLICY, evidence_path(job_id))
        c = checked["bundle"]["capture"]
        if c["source_id"] != source_id or checked["bundle"]["job"]["receipt"]["job_id"] != job_id:
            raise Rejected("audit source/job mismatch")
        return {"state": "verified_local_pinned_source", "source_id": source_id,
                "job_id": job_id, "source_sha256": c["content_sha256"],
                "evidence_sha256": checked["evidence_sha256"]}

    broker = SourceBroker(args.socket, set(args.allowed_uid), set(PINNED_POLICY), capture, audit)
    broker.start()
    stopped = False
    def stop(_signum, _frame):
        nonlocal stopped
        stopped = True
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        while not stopped:
            try:
                broker.accept_once()
            except socket.timeout:
                continue
    finally:
        broker.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
