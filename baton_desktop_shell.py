"""Official ChatGPT client is a managed peer to Baton, not an embedded webview.

This layer never reads cookies, private app files, or reverse-engineers the
ChatGPT client. All model->Greg operations still use authenticated Baton MCP.
"""
import os
from pathlib import Path
import shutil
import subprocess


def official_chatgpt_binary(*, which=None):
    finder = which if which is not None else shutil.which
    command = finder("chatgpt")
    if not command:
        return None
    path = Path(command)
    if not path.is_file() or not os.access(path, os.X_OK):
        return None
    return str(path)


def launch_official_chatgpt(*, which=None, spawn=None):
    command = official_chatgpt_binary(which=which)
    if command is None:
        return {"ok": False, "reason": "official-chatgpt-not-installed"}
    runner = spawn if spawn is not None else subprocess.Popen
    try:
        runner([command], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
               stderr=subprocess.DEVNULL, start_new_session=True)
    except OSError:
        return {"ok": False, "reason": "official-chatgpt-launch-failed"}
    return {"ok": True, "reason": "official-chatgpt-launch-requested"}


def shell_capabilities(chatgpt_found):
    """Distinguish operational capabilities from future messaging connectors."""
    return {
        "baton_core": "local",
        "chatgpt_client": "available" if chatgpt_found else "not-installed",
        "greg_mcp": "configured-client-required",
        "external_channels": "not-connected",
        "external_posting": "not-connected",
    }
