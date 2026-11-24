#!/usr/bin/env python3
"""Safely fast-forward an existing Baton checkout to one pinned branch.

This updater is intentionally narrow:
- no shell
- no branch switching
- no force/reset
- no dirty-worktree overwrite
- exact origin + branch match
- fast-forward only
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import subprocess
import sys

BRANCH_RE = re.compile(r"^[A-Za-z0-9._/-]{1,160}$")


class UpdateError(RuntimeError):
    pass


def _git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    env = {
        "PATH": "/usr/bin:/bin",
        "HOME": str(Path.home()),
        "LANG": "C",
        "LC_ALL": "C",
    }
    proc = subprocess.run(
        ["/usr/bin/git", "-C", str(root), *args],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=30,
        env=env,
        check=False,
        close_fds=True,
    )
    if check and proc.returncode != 0:
        raise UpdateError("git " + " ".join(args[:2]) + " failed")
    return proc


def safe_fast_forward(checkout: str | Path, *, expected_origin: str, expected_branch: str) -> dict:
    root = Path(checkout).expanduser()
    if root.is_symlink():
        raise UpdateError("checkout symlink rejected")
    root = root.resolve(strict=True)
    if not root.is_dir() or not (root / ".git").is_dir() or (root / ".git").is_symlink():
        raise UpdateError("checkout must be a normal git worktree")
    if not expected_origin.startswith("https://github.com/") or not expected_origin.endswith(".git"):
        raise UpdateError("unexpected origin policy")
    if not BRANCH_RE.fullmatch(expected_branch) or ".." in expected_branch:
        raise UpdateError("invalid branch")

    origin = _git(root, "config", "--get", "remote.origin.url").stdout.strip()
    branch = _git(root, "branch", "--show-current").stdout.strip()
    if origin != expected_origin:
        raise UpdateError("origin mismatch")
    if branch != expected_branch:
        raise UpdateError("branch mismatch")

    dirty = _git(root, "status", "--porcelain=v1", "--untracked-files=all").stdout
    if dirty:
        raise UpdateError("worktree has local changes; refusing update")

    before = _git(root, "rev-parse", "--verify", "HEAD").stdout.strip()
    remote_ref = f"refs/remotes/origin/{expected_branch}"
    refspec = f"+refs/heads/{expected_branch}:{remote_ref}"
    _git(root, "fetch", "--no-tags", "--prune", "origin", refspec)
    target = _git(root, "rev-parse", "--verify", remote_ref).stdout.strip()

    if before == target:
        return {"state": "already-current", "before": before, "after": before}

    ancestry = _git(root, "merge-base", "--is-ancestor", before, target, check=False)
    if ancestry.returncode != 0:
        raise UpdateError("remote branch is not a fast-forward of installed Baton")

    _git(root, "merge", "--ff-only", target)
    after = _git(root, "rev-parse", "--verify", "HEAD").stdout.strip()
    if after != target:
        raise UpdateError("post-update revision mismatch")

    return {"state": "updated", "before": before, "after": after}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkout", required=True)
    parser.add_argument("--origin", required=True)
    parser.add_argument("--branch", required=True)
    args = parser.parse_args(argv)
    if os.geteuid() == 0:
        parser.error("run as the normal Baton desktop user, never root")
    try:
        result = safe_fast_forward(
            args.checkout, expected_origin=args.origin, expected_branch=args.branch
        )
    except (OSError, subprocess.SubprocessError, UpdateError) as exc:
        print("Baton update refused:", str(exc), file=sys.stderr)
        return 1
    print(result["state"] + " " + result["after"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
