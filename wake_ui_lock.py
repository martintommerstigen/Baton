"""Host-local, cross-process exclusion for authorized ChatGPT UI writers.

All Baton UI runners on one host share this lock regardless of their ledger
path. It is advisory; it does not protect against unrelated browser writers.
"""
from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import stat

DEFAULT_LOCK_PATH = Path.home() / ".cache" / "baton" / "chatgpt-ui.lock"


@contextmanager
def ui_controller_lock(path=None):
    """Fail closed if another cooperating UI controller owns the host lock."""
    path = Path(path) if path is not None else DEFAULT_LOCK_PATH
    if not path.is_absolute() or '..' in path.parts:
        raise PermissionError('UI lock path must be absolute and without traversal')
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    for ancestor in reversed(path.parents):
        if not stat.S_ISDIR(os.lstat(ancestor).st_mode):
            raise PermissionError('UI lock ancestor must not be a symlink')
    directory = path.parent.stat()
    if (not stat.S_ISDIR(directory.st_mode) or directory.st_uid != os.getuid()
            or directory.st_mode & 0o022):
        raise PermissionError("UI lock directory must be owned by this user and not writable by others")
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW, 0o600)
    try:
        lock = os.fstat(fd)
        if (not stat.S_ISREG(lock.st_mode) or lock.st_uid != os.getuid()
                or lock.st_mode & 0o077 or lock.st_nlink != 1):
            raise PermissionError("UI lock file must be private and owned by this user")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("Another Baton UI controller holds the host lock; no send attempted") from exc
        current = os.lstat(path)
        if (current.st_dev, current.st_ino) != (lock.st_dev, lock.st_ino):
            raise PermissionError('UI lock inode changed before critical section')
        try:
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)
