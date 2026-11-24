"""Local pause probe for future UI adapters, never a send authorization token.

A read-only HTTP pause-status response is only an observation at one instant.
The actual UI adapter must recheck this path at the click boundary and must
not treat absence as sufficient authorization (allowlist and source evidence
are separate). A non-cooperating writer can still race the last check; full
atomicity requires the pause writer and UI sender to share a lock protocol.
"""
import os


class UIWritesPaused(PermissionError):
    pass


def pause_active(path):
    try:
        os.lstat(path)
        return True
    except FileNotFoundError:
        return False
    except OSError:
        return True


def require_not_paused_now(path):
    if pause_active(path):
        raise UIWritesPaused('PAUSE_UI_WRITES active or unreadable')
    return None  # never return a reusable permission lease
