"""Private, one-shot raw capture bundle storage for B5/B2 research evidence.

The source is read-only. Only an owner-only, exclusive local evidence file is
created. No overwrite, symlink traversal, shell, network, UI or blind retry.
"""
from __future__ import annotations

import hashlib
import json
import os
import stat

from remote_security.private_store import _validate_path
from remote_security.research_jobs import canonical, _unique_pairs, UntrustedReceipt
from remote_security.proc_stat_capture import verify_capture

MAX_BUNDLE = 32768


def save_verified_capture(jobs, bundle, path):
    """Verify then create one private raw-data artifact, never overwrite."""
    verify_capture(jobs, bundle)
    data = canonical(bundle)
    if len(data) > MAX_BUNDLE:
        raise ValueError("capture bundle exceeds bounded evidence size")
    p = _validate_path(path)
    flags = (os.O_WRONLY | os.O_CREAT | os.O_EXCL
             | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0))
    fd = os.open(p, flags, 0o600)
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or info.st_mode & 0o077 or info.st_nlink != 1):
            raise PermissionError("capture artifact must be private regular file")
        with os.fdopen(fd, "wb", closefd=False) as stream:
            stream.write(data)
            stream.flush()
            os.fsync(fd)
    finally:
        os.close(fd)
    # Persist the directory entry before claiming a durable local artifact.
    parent_fd = os.open(p.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
                        | getattr(os, "O_NOFOLLOW", 0))
    try:
        os.fsync(parent_fd)
    finally:
        os.close(parent_fd)
    return {"path": str(p), "sha256": hashlib.sha256(data).hexdigest(),
            "bytes": len(data), "state": "private_capture_saved_once"}


def load_verified_capture(jobs, path):
    """Read a private canonical artifact and reconcile with durable SQLite."""
    p = _validate_path(path)
    flags = (os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
             | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NONBLOCK", 0))
    fd = os.open(p, flags)
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or info.st_mode & 0o077 or info.st_nlink != 1):
            raise PermissionError("capture artifact must be owner-only regular file")
        data = os.read(fd, MAX_BUNDLE + 1)
    finally:
        os.close(fd)
    if len(data) > MAX_BUNDLE:
        raise UntrustedReceipt("capture artifact oversized")
    try:
        bundle = json.loads(data.decode("ascii"), object_pairs_hook=_unique_pairs)
        if canonical(bundle) != data:
            raise ValueError("noncanonical capture")
    except (UnicodeError, ValueError, TypeError) as exc:
        raise UntrustedReceipt("invalid capture artifact") from exc
    verify_capture(jobs, bundle)
    return bundle
