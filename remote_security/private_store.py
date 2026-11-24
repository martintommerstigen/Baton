"""Conservative SQLite path gate for an unprivileged Linux Baton agent.

Rejects symlink traversal, shared-writable database parents, foreign-owned or
permissive database files. It is not a sandbox against processes running with
this same UID. Never run the gateway as root.
"""
from __future__ import annotations

import os
from pathlib import Path
import sqlite3
import stat


class UnsafeStore(ValueError):
    """A database path is not suitable for an unprivileged Baton agent."""


def _validate_path(path):
    raw = os.fspath(path)
    if not isinstance(raw, str) or not raw.startswith('/'):
        raise UnsafeStore('absolute database path required')
    parts = raw.split('/')
    if any(part in ('', '.', '..') for part in parts[1:]):
        raise UnsafeStore('path normalization or traversal forbidden')
    p = Path(raw)
    if p.name in ('', '.', '..'):
        raise UnsafeStore('database filename required')
    uid = os.getuid()
    current = Path('/')
    for part in p.parent.parts[1:]:
        current = current / part
        try:
            s = current.lstat()
        except OSError as exc:
            raise UnsafeStore('database parent inaccessible') from exc
        if not stat.S_ISDIR(s.st_mode):
            raise UnsafeStore('database parent must be a real directory')
        # Shared writable ancestors are safe only when owned by root and
        # sticky (e.g. /tmp). The final parent must always be owner-only.
        if s.st_mode & 0o022 and not (s.st_uid == 0 and s.st_mode & stat.S_ISVTX):
            raise UnsafeStore('shared-writable ancestor')
    try:
        parent = p.parent.lstat()
    except OSError as exc:
        raise UnsafeStore('database parent inaccessible') from exc
    if parent.st_uid != uid or parent.st_mode & 0o077:
        raise UnsafeStore('database parent must be owned by agent and mode 0700')
    return p


def secure_database_path(path):
    """Create or check an owner-only regular DB file, never following a link.

    SQLite will subsequently reopen this pathname and create journal files in
    the checked private directory. A process with the same UID could still
    race a rename; the service must run under a dedicated, trusted UID.
    """
    p = _validate_path(path)
    flags = os.O_RDWR | os.O_CREAT | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_CLOEXEC', 0)
    try:
        fd = os.open(p, flags, 0o600)
    except OSError as exc:
        raise UnsafeStore('database file cannot be safely opened') from exc
    try:
        s = os.fstat(fd)
        if not stat.S_ISREG(s.st_mode) or s.st_uid != os.getuid() or s.st_mode & 0o077:
            raise UnsafeStore('database file must be owner-owned regular mode 0600')
        # Reject a hardlink to another file: the DB must have one pathname.
        if s.st_nlink != 1:
            raise UnsafeStore('database hardlinks forbidden')
    finally:
        os.close(fd)
    return str(p)


def connect_private(path):
    checked = secure_database_path(path)
    conn = sqlite3.connect(checked, timeout=10, isolation_level=None)
    conn.execute('PRAGMA busy_timeout=10000')
    conn.execute('PRAGMA secure_delete=ON')
    return conn
