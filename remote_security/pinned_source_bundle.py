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


def _check_pinned_parent(path, directory_fd):
    """Fail closed if the public evidence directory no longer names this fd.

    The service UID is a trusted boundary. This prevents accidental writes to
    a replaced path; it does not defend against arbitrary same-UID code.
    """
    _validate_path(path)
    pinned = os.fstat(directory_fd)
    current = path.parent.lstat()
    if (not stat.S_ISDIR(pinned.st_mode) or not stat.S_ISDIR(current.st_mode)
            or pinned.st_uid != os.getuid() or pinned.st_mode & 0o077
            or (pinned.st_dev, pinned.st_ino) != (current.st_dev, current.st_ino)):
        raise PermissionError("evidence parent changed or became unsafe")



def _check_pinned_file(directory_fd, basename, original):
    """Require the public evidence basename still to name the opened inode."""
    current = os.stat(basename, dir_fd=directory_fd, follow_symlinks=False)
    if (not stat.S_ISREG(current.st_mode) or current.st_uid != os.getuid()
            or current.st_mode & 0o077 or current.st_nlink != 1
            or (current.st_dev, current.st_ino) != (original.st_dev, original.st_ino)):
        raise UntrustedReceipt("evidence basename replaced during operation")


def _open_pinned_parent(path):
    path = _validate_path(path)
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    directory_fd = os.open(path.parent, flags)
    try:
        _check_pinned_parent(path, directory_fd)
        return path, directory_fd
    except BaseException:
        os.close(directory_fd)
        raise


def save_pinned_bundle(jobs, policy, bundle, path):
    """Verify, then exclusively persist one source bundle; never overwrite.

    Both file creation and parent fsync use the SAME validated directory fd.
    A directory replacement produces an uncertain result, not a retry permit.
    """
    verify_pinned_source(jobs, policy, bundle)
    data = canonical(bundle)
    if len(data) > MAX_EVIDENCE:
        raise ValueError("pinned source evidence exceeds bounded size")
    p, directory_fd = _open_pinned_parent(path)
    try:
        _check_pinned_parent(p, directory_fd)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC
        fd = os.open(p.name, flags, 0o600, dir_fd=directory_fd)
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
        _check_pinned_parent(p, directory_fd)
        os.fsync(directory_fd)
        _check_pinned_parent(p, directory_fd)
        _check_pinned_file(directory_fd, p.name, s)
    finally:
        os.close(directory_fd)
    return {"state": "private_pinned_bundle_saved_once", "sha256": hashlib.sha256(data).hexdigest(),
            "bytes": len(data)}


def load_pinned_bundle(jobs, policy, path):
    """Read an exact private artifact through a pinned directory capability."""
    p, directory_fd = _open_pinned_parent(path)
    try:
        _check_pinned_parent(p, directory_fd)
        fd = os.open(p.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK,
                     dir_fd=directory_fd)
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
            if (len(data) > MAX_EVIDENCE or len(data) != before.st_size
                    or fingerprint(before) != fingerprint(after)):
                raise UntrustedReceipt("source evidence changed during read")
        finally:
            os.close(fd)
        _check_pinned_parent(p, directory_fd)
        _check_pinned_file(directory_fd, p.name, before)
    finally:
        os.close(directory_fd)
    try:
        bundle = json.loads(data.decode("ascii"), object_pairs_hook=_unique_pairs)
        if canonical(bundle) != data:
            raise ValueError("noncanonical evidence")
    except (ValueError, UnicodeError, TypeError, RecursionError) as exc:
        raise UntrustedReceipt("invalid source evidence") from exc
    verification = verify_pinned_source(jobs, policy, bundle)
    return {"bundle": bundle, "verification": verification,
            "evidence_sha256": hashlib.sha256(data).hexdigest()}
