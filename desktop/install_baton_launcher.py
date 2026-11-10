#!/usr/bin/env python3
"""Install a local-only Baton desktop launcher without credentials or shell interpolation.

The launcher opens a terminal with Baton's existing CLI help; it does NOT
start a network service, connect to ChatGPT, or claim delivery verification.
"""
import argparse
import os
from pathlib import Path
import shlex
import sys

DESKTOP_TEMPLATE = """[Desktop Entry]
Type=Application
Name=Baton (local CLI)
Comment=Open Baton command-line help; no server or network started
Exec={command}
Icon=utilities-terminal
Terminal=true
Categories=Utility;Development;
StartupNotify=false
"""

def desktop_entry(python_executable, client_path):
    python_executable = Path(python_executable).resolve(strict=True)
    client_path = Path(client_path).resolve(strict=True)
    if not python_executable.is_file() or not client_path.is_file():
        raise ValueError("Expected regular files")
    if client_path.name != "client.py":
        raise ValueError("Select the Baton client.py")
    # Desktop Exec is not a shell; quote arguments according to desktop-entry syntax.
    # Restrict paths to avoid ambiguous desktop field codes and escaping.
    for path in (python_executable, client_path):
        if any(c in str(path) for c in ('%', '"', '\\', '\n', '\r')):
            raise ValueError("Unsupported character in executable path")
    command = f'"{python_executable}" "{client_path}" --help'
    return DESKTOP_TEMPLATE.format(command=command)

def install(client_path, destination=None):
    destination = Path(destination or Path.home() / ".local/share/applications/baton-local.desktop")
    if destination.is_symlink():
        raise ValueError("Refusing symlink destination")
    destination.parent.mkdir(parents=True, exist_ok=True)
    data = desktop_entry(sys.executable, client_path)
    temp = destination.with_name(destination.name + ".tmp-" + str(os.getpid()))
    try:
        with temp.open("x", encoding="utf-8") as f:
            f.write(data)
        os.chmod(temp, 0o644)
        os.replace(temp, destination)
    finally:
        temp.unlink(missing_ok=True)
    return destination

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client", default=str(Path(__file__).resolve().parents[1] / "client.py"))
    parser.add_argument("--destination", default=None)
    args = parser.parse_args()
    print(install(args.client, args.destination))

if __name__ == "__main__":
    main()
