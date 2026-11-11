"""Host-local, cross-process exclusion for authorized ChatGPT UI writers.

All Baton UI runners on one host share this lock regardless of their ledger
path. It is advisory; it does not protect against unrelated browser writers.
A post-submission identity check detects persistent same-UID path replacement
and fails closed, but cannot undo a click or prevent transient split-lock races.
"""
from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import stat

DEFAULT_LOCK_PATH = Path.home() / ".cache" / "baton" / "chatgpt-ui.lock"

def _assert_lock_binding(path, directory, lock):
    """Reject a persistent same-UID lock/path swap while the flock is held.

    Detection is NOT prevention of a transient split-lock race. In particular,
    a click may already have happened: callers must retain delivery uncertainty.
    """
    try:
        current_dir = os.lstat(path.parent)
        current_lock = os.lstat(path)
    except OSError as exc:
        raise PermissionError(
            "UI lock pathname disappeared during submission; delivery uncertain"
        ) from exc
    if (not stat.S_ISDIR(current_dir.st_mode)
            or (current_dir.st_dev, current_dir.st_ino)
            != (directory.st_dev, directory.st_ino)
            or current_dir.st_uid != os.getuid()
            or current_dir.st_mode & 0o022
            or not stat.S_ISREG(current_lock.st_mode)
            or (current_lock.st_dev, current_lock.st_ino)
            != (lock.st_dev, lock.st_ino)
            or current_lock.st_uid != os.getuid()
            or current_lock.st_mode & 0o077
            or current_lock.st_nlink != 1):
        raise PermissionError(
            "UI lock identity changed during submission; delivery uncertain"
        )



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
            try:
                yield
            finally:
                # Check before releasing the old inode's flock. A post-click
                # mismatch cannot be reported as successful delivery.
                _assert_lock_binding(path, directory, lock)
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


class LockingUIDriver:
    """Hold the shared host UI lock only across one actual submission.

    Observing an assistant response does not need the write lock. Releasing it
    during generation permits another authorized conversation's independent
    action, as Riss R20's 7 Nov Greg test required. This wrapper never retries.
    Verified broker admission still serializes outstanding target attempts.
    """

    def __init__(self, driver, lock_path=None):
        self.driver = driver
        self.lock_path = lock_path

    def submit_once(self, *args, **kwargs):
        # Includes exact composer readback, broker begin_click and Send click.
        # Failure to acquire is conservative: wake_once retains uncertainty.
        with ui_controller_lock(self.lock_path):
            return self.driver.submit_once(*args, **kwargs)

    def __getattr__(self, name):
        return getattr(self.driver, name)
