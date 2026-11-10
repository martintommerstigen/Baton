"""Local, opt-in command adapter for Baton.

No network listener, shell, arbitrary command strings or ChatGPT cookie access.
The caller must already have a trusted local path to this process.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

COMMANDS = {
    "identity": ("/usr/bin/id",),
    "system": ("/usr/bin/uname", "-a"),
    "git-status": ("/usr/bin/git", "status", "--short", "--branch"),
    "git-revision": ("/usr/bin/git", "rev-parse", "HEAD"),
    "cargo-version": ("/usr/bin/cargo", "--version"),
    "python-version": (sys.executable, "--version"),
}
MAX_OUTPUT = 16384

def execute(operation, workspace):
    if operation not in COMMANDS:
        raise ValueError("operation not allowlisted")
    root = Path(workspace).resolve(strict=True)
    if not root.is_dir():
        raise ValueError("workspace must be a directory")
    if operation.startswith("git-") and not (root / ".git").exists():
        raise ValueError("not a git checkout")
    command = COMMANDS[operation]
    executable = Path(command[0])
    if not executable.is_file():
        return {"ok": False, "error": "executable unavailable"}
    try:
        result = subprocess.run(
            command, cwd=root, shell=False, stdin=subprocess.DEVNULL,
            capture_output=True, timeout=5, check=False,
            env={"PATH": "/usr/bin:/bin", "LANG": "C", "HOME": str(Path.home())},
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "timeout"}
    output = (result.stdout + result.stderr)[:MAX_OUTPUT].decode("utf-8", "replace")
    return {"ok": result.returncode == 0, "exit_code": result.returncode,
            "output": output, "truncated": len(result.stdout) + len(result.stderr) > MAX_OUTPUT}

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=sorted(COMMANDS))
    parser.add_argument("--workspace", required=True)
    args = parser.parse_args(argv)
    try:
        print(json.dumps(execute(args.operation, args.workspace)))
        return 0
    except (ValueError, OSError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
