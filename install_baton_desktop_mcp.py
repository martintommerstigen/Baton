#!/usr/bin/env python3
"""Install Baton's STDIO MCP tool in local ChatGPT desktop/Codex config.

Requires explicit one-time user invocation; never runs on import or modifies
the ChatGPT website. Existing unrelated TOML configuration is preserved.
"""
import argparse
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
import tomllib

SECTION = "mcp_servers.baton_greg"


def configured_server(script, executable="/usr/bin/python3"):
    script = Path(script).resolve(strict=True)
    if not script.is_file() or script.name != "baton_mcp_stdio.py":
        raise ValueError("Baton MCP script missing")
    if not Path(executable).is_file():
        raise ValueError("Python executable not found")
    return "\n".join([
        "# Baton direct MCP: tools work only while local Baton Core is running.",
        "[" + SECTION + "]",
        "command = " + json.dumps(str(executable)),
        "args = [" + json.dumps(str(script)) + "]",
        "cwd = " + json.dumps(str(script.parent)),
        "enabled = true",
        "tool_timeout_sec = 100",
        "# User authorized full ordinary-user execution while Baton is open.",
        "# Change auto to prompt to require consent for every tool call.",
        "default_tools_approval_mode = \"auto\"",
        ""
    ])


def install(config_path, script, executable="/usr/bin/python3"):
    config_path = Path(config_path).expanduser()
    if config_path.is_symlink():
        raise ValueError("config file symlink is not allowed")
    config_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if config_path.parent.is_symlink():
        raise ValueError("config directory symlink is not allowed")
    if config_path.exists() and not config_path.is_file():
        raise ValueError("config is not a regular file")
    prior = config_path.read_text(encoding="utf-8") if config_path.exists() else ""
    parsed = tomllib.loads(prior) if prior.strip() else {}
    existing = parsed.get("mcp_servers", {}).get("baton_greg")
    block = configured_server(script, executable)
    desired = tomllib.loads(block)["mcp_servers"]["baton_greg"]
    if existing is not None:
        if existing == desired:
            return "already-configured"
        raise ValueError("existing baton_greg config differs; review it manually")
    if not isinstance(parsed.get("mcp_servers", {}), dict):
        raise ValueError("incompatible MCP config")
    new_text = prior.rstrip() + ("\n\n" if prior.strip() else "") + block
    assert tomllib.loads(new_text)["mcp_servers"]["baton_greg"] == desired
    mode = 0o600
    if config_path.exists():
        mode = stat.S_IMODE(config_path.stat().st_mode) & 0o600
    fd, temporary = tempfile.mkstemp(prefix=".baton-mcp-", dir=config_path.parent)
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            out.write(new_text)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temporary, config_path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return "installed"


def main():
    parser = argparse.ArgumentParser(description="Register Baton tools in ChatGPT Linux desktop")
    parser.add_argument("--config", default=str(Path.home()/".codex/config.toml"))
    parser.add_argument("--python", default="/usr/bin/python3")
    args = parser.parse_args()
    if os.geteuid() == 0:
        parser.error("do not run as root")
    try:
        outcome = install(args.config, Path(__file__).with_name("baton_mcp_stdio.py"), args.python)
    except (OSError, ValueError, tomllib.TOMLDecodeError) as exc:
        parser.error(str(exc))
    print("Baton MCP", outcome, "in", args.config)
    print("Open official ChatGPT Linux desktop > Settings > MCP servers, then restart.")
    print("Keep Baton open; closing Baton stops local Core and tool execution.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
