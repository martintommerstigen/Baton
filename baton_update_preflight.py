"""Read-only Baton deployment preflight; does not update or restart Greg.

An update is deliberately a separate human-approved operation until a signed,
rollback-capable updater has been verified. Never use remote request text as shell.
"""
from pathlib import Path
import json
import subprocess

REQUIRED = ("baton_github_bus.py", "baton_local_terminal.py", "test_baton_github_bus.py")

def inspect_checkout(path):
    root = Path(path).expanduser()
    if root.is_symlink() or not root.is_dir():
        return {"ok": False, "reason": "invalid_checkout"}
    if any((root / name).is_symlink() or not (root / name).is_file() for name in REQUIRED):
        return {"ok": False, "reason": "missing_or_linked_files"}
    proc = subprocess.run(["/usr/bin/git", "rev-parse", "--verify", "HEAD"],cwd=root,
                          stdin=subprocess.DEVNULL,capture_output=True,text=True,timeout=5)
    if proc.returncode or len(proc.stdout.strip()) != 40:
        return {"ok": False, "reason": "invalid_git_revision"}
    return {"ok": True, "revision": proc.stdout.strip(), "update_performed": False}

if __name__ == "__main__":
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("--checkout", default=str(Path.home()/".local/share/baton-evening"))
    args=p.parse_args()
    result=inspect_checkout(args.checkout)
    print(json.dumps(result,sort_keys=True))
    raise SystemExit(0 if result["ok"] else 1)
