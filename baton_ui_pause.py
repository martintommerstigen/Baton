"""Fail-closed Greg-local pause gate for all Baton-driven ChatGPT UI writes.

This does not revoke normal user filesystem access or terminate Baton.
A positive/uncertain pause gate prevents programmatic UI Send clicks and
never clears PAUSE_UI_WRITES. Only a separate verified recovery may lift it.
"""
from pathlib import Path


PAUSE_PATH = Path.home() / "GTRCM-newborn-bootstrap" / "transport" / "PAUSE_UI_WRITES"


def ui_writes_paused(path=PAUSE_PATH):
    """Missing flag = not paused; any present object or unreadable state = paused.

    lstat sees dangling symlinks. Fail closed for permission, IO, and other
    errors rather than treating a failed safety check as authorization.
    """
    try:
        Path(path).lstat()
    except FileNotFoundError:
        return False
    except (OSError, TypeError, ValueError):
        return True
    return True
