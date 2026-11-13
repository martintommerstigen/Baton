"""Owner-private SQLite path gate for Baton reference stores.

This prevents accidental first-open exposure (umask 022), symlink and
hardlink redirection, and writes through a group/world-writable directory.
Call before every sqlite3.connect, not only during schema initialization.

It does not defend against a hostile process with the same OS identity that
can race a later sqlite3.connect; live Core needs its own process boundary.
"""
import os
from pathlib import Path
import stat


def prepare_private_sqlite(path):
    path = Path(path)
    # Reject traversal before absolute() or resolve() can obscure intent.
    # In particular, resolving symlinks would hide the very alias we check.
    if ".." in path.parts:
        raise ValueError("SQLite path traversal forbidden")
    path = path.absolute()
    parent = path.parent
    # An immediate-parent-only check misses /base/alias/child/db.sqlite3
    # when alias is a symlink but child is an ordinary directory.
    if any(ancestor.is_symlink() for ancestor in (parent, *parent.parents)):
        raise ValueError("SQLite symlinked ancestor forbidden")
    if not parent.is_dir():
        raise ValueError("SQLite parent must be a real directory")
    pstat = parent.stat()
    if pstat.st_uid != os.geteuid() or pstat.st_mode & 0o022:
        raise PermissionError("SQLite parent must be owner-controlled")

    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        fd = os.open(path, flags, 0o600)
    except OSError as exc:
        if path.is_symlink():
            raise ValueError("SQLite symlink forbidden") from exc
        raise
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or info.st_nlink != 1):
            raise ValueError("SQLite database must be a single-link owner file")
        os.fchmod(fd, 0o600)
        current = path.stat(follow_symlinks=False)
        if (not stat.S_ISREG(current.st_mode)
                or (current.st_dev, current.st_ino) != (info.st_dev, info.st_ino)):
            raise ValueError("SQLite path changed while preparing")
    finally:
        os.close(fd)
