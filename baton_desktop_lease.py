"""Liveness lease: local ChatGPT MCP write tools work only while Baton UI runs.

This is a local same-user safety interlock, not an authentication credential.
The private Core bearer token and OS permissions remain the security boundary.
"""
import json
import os
from pathlib import Path
import stat
import tempfile


def lease_path():
    return Path.home() / ".local/state/baton/active-chatgpt-ui.json"


def _start_ticks(pid):
    """Linux process start time, avoiding PID reuse after a crash."""
    try:
        raw = Path(f"/proc/{int(pid)}/stat").read_text(encoding="utf-8")
        return int(raw.rsplit(") ", 1)[1].split()[19])
    except (OSError, ValueError, IndexError):
        return None


def create_ui_lease(path=None):
    target = Path(path) if path is not None else lease_path()
    if target.is_symlink():
        raise ValueError("UI lease symlink forbidden")
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if target.parent.is_symlink():
        raise ValueError("UI lease directory symlink forbidden")
    ticks = _start_ticks(os.getpid())
    if ticks is None:
        raise RuntimeError("Linux process identity unavailable")
    marker = {"pid": os.getpid(), "start_ticks": ticks}
    fd, temp_path = tempfile.mkstemp(prefix=".baton-ui-", dir=target.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(marker, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, target)
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)
    return marker


def ui_lease_active(path=None):
    target = Path(path) if path is not None else lease_path()
    try:
        if target.is_symlink() or not target.is_file():
            return False
        mode = target.stat().st_mode
        if not stat.S_ISREG(mode) or mode & 0o077:
            return False
        marker = json.loads(target.read_text(encoding="utf-8"))
        if not isinstance(marker, dict) or set(marker) != {"pid", "start_ticks"}:
            return False
        pid, ticks = marker["pid"], marker["start_ticks"]
        if type(pid) is not int or type(ticks) is not int or pid < 1:
            return False
        return _start_ticks(pid) == ticks
    except (OSError, UnicodeError, ValueError, TypeError):
        return False


def release_ui_lease(marker, path=None):
    target = Path(path) if path is not None else lease_path()
    try:
        if target.is_symlink():
            return
        if json.loads(target.read_text(encoding="utf-8")) == marker:
            target.unlink()
    except (OSError, ValueError, TypeError):
        return
