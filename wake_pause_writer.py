"""Cooperative, fail-closed PAUSE_UI_WRITES writer for Baton existing-chat UI.

This is a local, one-way PAUSE operation; it never clears a pause or sends UI
messages. It shares the host UI flock with the existing Baton wake runners.
"""
import json
import os
from pathlib import Path

from chatgpt_ui_driver import PAUSE_FILE
from wake_ui_lock import ui_controller_lock

_DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
_FILE_FLAGS = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC


def _create_pause_marker(path):
    """Create a private marker through no-follow directory descriptors.

    Returns False when a marker already exists, including a symlink marker.
    Any unsafe/missing ancestor raises without following its link.
    """
    path = Path(path)
    if not path.is_absolute() or '..' in path.parts or len(path.parts) < 2:
        raise ValueError('pause path must be absolute and without traversal')
    directory_fd = os.open('/', _DIRECTORY_FLAGS)
    try:
        for part in path.parts[1:-1]:
            next_fd = os.open(part, _DIRECTORY_FLAGS, dir_fd=directory_fd)
            os.close(directory_fd)
            directory_fd = next_fd
        try:
            fd = os.open(path.name, _FILE_FLAGS, 0o600, dir_fd=directory_fd)
        except FileExistsError:
            return False
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        os.fsync(directory_fd)
        return True
    finally:
        os.close(directory_fd)


def activate_pause(path=PAUSE_FILE, lock_path=None):
    """Serialize pause creation with cooperating UI senders.

    The lock is nonblocking: when a send is in progress, this raises and does
    NOT claim a pause. The operator may retry explicitly after the sender exits.
    This does not control noncooperating writers or other browser users.
    """
    with ui_controller_lock(lock_path):
        return _create_pause_marker(path)


def main():
    # No path/lock override in the production CLI: tests inject temporary paths
    # through the Python API. Never clear PAUSE_UI_WRITES automatically.
    created = activate_pause()
    print(json.dumps({'state': 'paused', 'created': created, 'scope': 'cooperating-baton-ui'}))


if __name__ == '__main__':
    main()
