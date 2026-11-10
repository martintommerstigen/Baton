#!/usr/bin/env python3
"""Baton private-GitHub request/response transport (no inbound network port).

The private transport branch is a mailbox, NOT a place for arbitrary commands,
secrets, private files, or unbounded logs. Only the local fixed allowlist runs.
GitHub credentials stay on Greg. This script never executes remote text.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

from baton_local_terminal import execute

REMOTE_HTTPS = "https://github.com/martintommerstigen/GTRCM.git"
REMOTE_SSH = "git@github.com:martintommerstigen/GTRCM.git"
BRANCH = "transport/baton-greg-bus-2026-11-10"
MARKER = ".baton-greg-bus/README"
ROOT = ".baton-greg-bus"
OPERATIONS = frozenset(("identity", "system", "git-revision", "python-version"))
NONCE = re.compile(r"[0-9a-f]{32}\Z")
MAX_AGE = 6 * 3600
MAX_REQUEST_BYTES = 1024

def git(*args, cwd=None, timeout=35):
    cmd = ["git", "-c", "core.hooksPath=/dev/null",
           "-c", "commit.gpgsign=false", *args]
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    result = subprocess.run(cmd, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                            capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError("Git operation failed: " + args[0] +
                           " (check authentication, connection and branch)")
    return result.stdout.strip()

def ensure_checkout(worktree, remote):
    if worktree.is_symlink():
        raise RuntimeError("Refusing symlinked transport checkout")
    if not worktree.exists():
        worktree.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        git("clone", "--depth=1", "--filter=blob:none", "--single-branch",
            "--branch", BRANCH, remote, str(worktree), timeout=90)
    if not (worktree / ".git").is_dir() or (worktree / ".git").is_symlink():
        raise RuntimeError("Not a real transport checkout")
    origin = git("remote", "get-url", "origin", cwd=worktree)
    if origin not in (REMOTE_HTTPS, REMOTE_SSH):
        raise RuntimeError("Unexpected repository origin")
    git("fetch", "--depth=1", "origin", BRANCH, cwd=worktree)
    git("reset", "--hard", "FETCH_HEAD", cwd=worktree)
    marker = worktree / MARKER
    if marker.is_symlink() or not marker.is_file() or marker.read_text().strip() != "BATON-GREG-BUS-V1":
        raise RuntimeError("Missing expected private transport marker")

def make_response(path, workspace, now):
    req_id = path.stem
    if not NONCE.fullmatch(req_id):
        return None
    try:
        if path.stat().st_size > MAX_REQUEST_BYTES or path.is_symlink():
            raise ValueError("invalid request file")
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or set(data) != {"id","operation","created_at"}:
            raise ValueError("invalid request shape")
        if data["id"] != req_id or not isinstance(data["operation"], str):
            raise ValueError("invalid request id/operation")
        if data["operation"] not in OPERATIONS:
            raise ValueError("operation not allowed")
        if not isinstance(data["created_at"], str):
            raise ValueError("invalid timestamp")
        when = datetime.fromisoformat(data["created_at"].replace("Z","+00:00"))
        if when.tzinfo is None:
            raise ValueError("missing request timezone")
        age = (now-when.astimezone(timezone.utc)).total_seconds()
        if not (-60 <= age <= MAX_AGE):
            raise ValueError("expired or future-dated request")
        outcome = execute(data["operation"], workspace)
        return {"id":req_id, "operation":data["operation"], "status":"executed", "result":outcome}
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        return {"id":req_id, "status":"rejected", "reason":type(exc).__name__}

def poll_once(worktree, remote, workspace, now=None):
    now = now or datetime.now(timezone.utc)
    if not workspace.is_dir() or workspace.is_symlink():
        raise RuntimeError("Expected Baton workspace unavailable")
    # Reset is safe ONLY in the dedicated Baton mailbox clone.
    ensure_checkout(worktree, remote)
    req_dir = worktree / ROOT / "requests"
    res_dir = worktree / ROOT / "responses"
    if not req_dir.is_dir() or req_dir.is_symlink() or res_dir.is_symlink():
        raise RuntimeError("Unsafe mailbox directory")
    res_dir.mkdir(exist_ok=True)
    count = 0
    # Bound the number of *new* requests, not the first 30 historical filenames.\n    # Otherwise old acknowledged requests can starve later requests forever.
    for path in sorted(req_dir.glob("*.json")):
        if not NONCE.fullmatch(path.stem) or (res_dir / path.name).exists():
            continue
        if count >= 30:
            break
        response = make_response(path, workspace, now)
        if response is None:
            continue
        (res_dir / path.name).write_text(json.dumps(response, sort_keys=True)+"\n", encoding="utf-8")
        count += 1
    if count:
        git("add", "--", ROOT + "/responses", cwd=worktree)
        git("-c", "user.name=Baton Greg", "-c", "user.email=baton-greg@users.noreply.github.com",
            "commit", "--no-verify", "-m", "baton: acknowledge bounded local requests", cwd=worktree)
        git("push", "origin", "HEAD:refs/heads/"+BRANCH, cwd=worktree)
    return count

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--transport", choices=["ssh","https"], default="https")
    p.add_argument("--worktree", default=str(Path.home()/".local/state/baton-greg-github-mailbox"))
    p.add_argument("--workspace", default=str(Path.home()/".local/share/baton-evening"))
    p.add_argument("--loop", action="store_true")
    p.add_argument("--interval", type=int, default=20)
    args=p.parse_args()
    if not 10 <= args.interval <= 3600:
        p.error("--interval must be between 10 and 3600")
    remote = REMOTE_SSH if args.transport == "ssh" else REMOTE_HTTPS
    while True:
        try:
            count=poll_once(Path(args.worktree).expanduser(),
                            remote, Path(args.workspace).expanduser())
            print(f"Baton mailbox: {count} request(s) processed", flush=True)
        except (RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
            print(f"Baton mailbox: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
            if not args.loop:
                return 1
        if not args.loop:
            return 0
        time.sleep(args.interval)

if __name__ == "__main__":
    raise SystemExit(main())
