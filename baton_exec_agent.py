"""Opt-in full user-level command execution over private Baton mailbox.

SECURITY: Anyone able to write requests on the transport branch can execute
commands with the agent user's privileges. Enable only with a dedicated private
repository, restricted GitHub collaborators, and an unprivileged local account.
Do not run as root. This is deliberately NOT enabled by the read-only bus.
"""
import os
from pathlib import Path
import subprocess

MAX_OUTPUT = 16000
MAX_SECONDS = 90

def execute_command(argv, cwd, timeout=30):
    if not isinstance(argv, list) or not 1 <= len(argv) <= 32:
        raise ValueError("argv must contain 1-32 arguments")
    if any(not isinstance(a, str) or not a or len(a) > 4096 or "\x00" in a for a in argv):
        raise ValueError("invalid argv")
    if not isinstance(cwd, str) or not cwd.startswith("/") or "\x00" in cwd:
        raise ValueError("cwd must be absolute")
    directory = Path(cwd).resolve(strict=True)
    if not directory.is_dir():
        raise ValueError("cwd must be a directory")
    if type(timeout) is not int or not 1 <= timeout <= MAX_SECONDS:
        raise ValueError("invalid timeout")
    if os.geteuid() == 0:
        raise PermissionError("refuse to run as root")
    try:
        result = subprocess.run(argv, cwd=directory, stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                timeout=timeout, check=False)
        output = result.stdout[:MAX_OUTPUT].decode("utf-8", errors="replace")
        return {"exit_code":result.returncode,"output":output,
                "truncated":len(result.stdout)>MAX_OUTPUT}
    except subprocess.TimeoutExpired as exc:
        output = (exc.stdout or b"")[:MAX_OUTPUT].decode("utf-8", errors="replace")
        return {"exit_code":None,"output":output,"truncated":True,"timeout":True}
