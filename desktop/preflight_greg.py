#!/usr/bin/env python3
"""Offline, read-only preflight. No network, credentials, or browser automation."""
import json
from pathlib import Path
import shutil
import sys

PAUSE_PATH = Path("/home/olliver/GTRCM-newborn-bootstrap/transport/PAUSE_UI_WRITES")

def check():
    home = Path.home()
    commands = {name: shutil.which(name) for name in ("git", "python3", "systemctl")}
    pause = PAUSE_PATH
    target = home / ".local/share/baton-evening"
    result = {
        "platform": sys.platform,
        "python": sys.version.split()[0],
        "commands_available": {name: bool(path) for name, path in commands.items()},
        "systemd_user_available": bool(commands["systemctl"]),
        "install_target_exists": target.exists() or target.is_symlink(),
        "install_target_symlink": target.is_symlink(),
        "ui_writes_paused_or_unverifiable": True,
        "ready_for_chatgpt_terminal": False,
    }
    # Fail closed: a missing marker alone is not proof of permission.
    try:
        ancestors = list(reversed(pause.parents))
        if all(p.is_dir() and not p.is_symlink() for p in ancestors):
            result["ui_writes_paused_or_unverifiable"] = pause.exists() or pause.is_symlink()
    except OSError:
        pass
    return result

if __name__ == "__main__":
    print(json.dumps(check(), indent=2, sort_keys=True))
