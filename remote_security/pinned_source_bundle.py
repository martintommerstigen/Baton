"""Durable private evidence for an operator-pinned RustWorld source read.

B5/R9: archived source checkout is never modified. Evidence is written
once, owner-only, and rechecked against the existing ResearchJobs SQLite ledger.
A failed save is uncertain, never permission to repeat the source job ID.
"""
from __future__ import annotations

import hashlib
import json
import os
import stat

from remote_security.private_store import _validate_path
from remote_security.research_jobs import canonical, _unique_pairs, UntrustedReceipt
from remote_security.pinned_source import verify_pinned_source

MAX_EVIDENCE = 262144  # source UTF-8 may expand when JSON-escaped


def save_pinned_bundle(jobs, policy, bundle, path):
    """Verify, then exclusively persist one source bundle; never overwrite."""
    verify_pinned_source(jobs, policy, bundle)
    data = canonical(bundle)
    if len(data) > MAX_EVIDENCE:
        raise ValueError("pinned source evidence exceeds bounded size")
    p = _validate_path(path)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC
    fd = os.open(p, flags, 0o600)
    try:
        s = os.fstat(fd)
        if (not stat.S_ISREG(s.st_mode) or s.st_uid != os.getuid()
                or s.st_mode & 0o077 or s.st_nlink != 1):
            raise PermissionError("source evidence must be a private regular file")
        remaining = memoryview(data)
        while remaining:
            written = os.write(fd, remaining)
            if written <= 0:
                raise OSError("short evidence write")
            remaining = remaining[written:]
        os.fsync(fd)
    finally:
        os.close(fd)
    # If fsync fails, an artifact may exist but durability is NOT established.
    parent_fd = os.open(p.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        os.fsync(parent_fd)
    finally:
        os.close(parent_fd)
    return {"state": "private_pinned_bundle_saved_once", "sha256": hashlib.sha256(data).hexdigest(),
            "bytes": len(data)}


def load_pinned_bundle(jobs, policy, path):
    """Read a private bounded artifact and reconcile its exact local receipt."""
    p = _validate_path(path)
    fd = os.open(p, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_uid != os.getuid()
                or before.st_mode & 0o077 or before.st_nlink != 1):
            raise PermissionError("source evidence must be owner-only and unlinked")
        if before.st_size > MAX_EVIDENCE:
            raise UntrustedReceipt("source evidence oversized")
        data = os.read(fd, MAX_EVIDENCE + 1)
        after = os.fstat(fd)
        fingerprint = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        if len(data) > MAX_EVIDENCE or len(data) != before.st_size or fingerprint(before) != fingerprint(after):
            raise UntrustedReceipt("source evidence changed during read")
    finally:
        os.close(fd)
    try:
        bundle = json.loads(data.decode("ascii"), object_pairs_hook=_unique_pairs)
        if canonical(bundle) != data:
            raise ValueError("noncanonical evidence")
    except (ValueError, UnicodeError, TypeError, RecursionError) as exc:
        raise UntrustedReceipt("invalid source evidence") from exc
    verification = verify_pinned_source(jobs, policy, bundle)
    return {"bundle": bundle, "verification": verification,
            "evidence_sha256": hashlib.sha256(data).hexdigest()}
