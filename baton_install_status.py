"""Read-only local inspection of the installed Baton stack.

Never opens a token file or prints credentials, session state, process argv,
repository remote URLs or message bodies. A TCP listener is not proof of
Baton Core authentication; Codex TOML is not proof of a ChatGPT tool session.
"""
import json
import os
from pathlib import Path
import shutil
import socket
import stat
import subprocess
import sys
import tomllib

from baton_desktop_lease import ui_lease_active


def _short_git(root, arguments, runner):
    try:
        p = runner(["git", "-C", str(root), *arguments],
                   capture_output=True, text=True, timeout=3, check=False)
        if p.returncode != 0:
            return None
        return p.stdout.strip()[:150]
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


def _service_active(runner):
    try:
        p = runner(["systemctl", "--user", "is-active", "baton-local-api.service"],
                   capture_output=True, text=True, timeout=3, check=False)
        return p.stdout.strip() == "active" and p.returncode == 0
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return False


def _port_open():
    try:
        with socket.create_connection(("127.0.0.1", 52526), timeout=0.3):
            return True
    except OSError:
        return False


def inspect_installation(*, root=None, home=None, runner=None, tcp_check=None,
                         lease_check=None, which=None):
    root = Path(root) if root is not None else Path(__file__).resolve().parent
    home = Path(home) if home is not None else Path.home()
    runner = runner if runner is not None else subprocess.run
    tcp_check = tcp_check if tcp_check is not None else _port_open
    lease_check = lease_check if lease_check is not None else ui_lease_active
    which = which if which is not None else shutil.which
    git_dir = root / ".git"
    branch = _short_git(root, ["rev-parse", "--abbrev-ref", "HEAD"], runner) if git_dir.exists() else None
    revision = _short_git(root, ["rev-parse", "HEAD"], runner) if git_dir.exists() else None
    changed = _short_git(root, ["status", "--porcelain"], runner) if git_dir.exists() else None
    clean = None if changed is None else (changed == "")
    token = home / ".config/baton/local-api-token"
    try:
        tok_stat = token.lstat()
        token_private = bool(stat.S_ISREG(tok_stat.st_mode) and not tok_stat.st_mode & 0o077)
    except OSError:
        token_private = False
    config = home / ".codex/config.toml"
    registered = False
    config_state = "absent"
    try:
        if config.is_symlink():
            config_state = "symlink-refused"
        elif config.is_file():
            if config.stat().st_size > 1048576:
                config_state = "too-large"
            else:
                parsed = tomllib.loads(config.read_text(encoding="utf-8"))
                entry = parsed.get("mcp_servers", {}).get("baton_greg", {})
                registered = bool(
                    isinstance(entry, dict)
                    and entry.get("enabled") is True
                    and isinstance(entry.get("args"), list)
                    and str(root / "baton_mcp_stdio.py") in entry["args"]
                )
                config_state = "registered-for-codex" if registered else "not-registered"
    except (OSError, ValueError, TypeError, tomllib.TOMLDecodeError):
        config_state = "invalid"
    entry_file = home / ".local/share/applications/baton.desktop"
    shortcut = False
    try:
        if not entry_file.is_symlink() and entry_file.is_file():
            raw = entry_file.read_text(encoding="utf-8")
            shortcut = "Name=Baton\n" in raw and str(root / "run_baton_direct.sh") in raw
    except (OSError, UnicodeError):
        pass
    client = which("chatgpt")
    return {
        "checkout_present": root.is_dir() and git_dir.exists(),
        "branch": branch,
        "revision": revision if revision and len(revision) == 40 else None,
        "clean_worktree": clean,
        "user_is_root": os.geteuid() == 0,
        "ui_lease_live": bool(lease_check()),
        "core_port_open_unverified": bool(tcp_check()),
        "core_service_active_unverified": _service_active(runner),
        "core_token_private_mode_only": token_private,
        "codex_mcp_config_state": config_state,
        "baton_desktop_entry_matches": shortcut,
        "official_chatgpt_binary_present": bool(client),
        "existing_chat_wake_verified": False
    }


def main():
    print(json.dumps(inspect_installation(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
