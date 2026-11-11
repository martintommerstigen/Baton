#!/usr/bin/env bash
# Start direct native MCP Baton Core; no embedded ChatGPT browser or text frames.
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${BATON_PYTHON:-python3}"
VENV="${BATON_QT_VENV:-$HOME/.local/share/baton/qt-venv}"
if [[ "$(id -u)" -eq 0 ]]; then
    echo "Never run Baton as root" >&2
    exit 1
fi
if [[ -z "${DISPLAY:-}" && -z "${WAYLAND_DISPLAY:-}" ]]; then
    echo "Start Baton from the graphical desktop session" >&2
    exit 1
fi
# The native Baton app is independent of any specific model client.
# Register Codex/ChatGPT MCP only with explicit opt-in; registration errors
# must not prevent users from opening Baton.
if [[ "${BATON_REGISTER_MCP:-0}" == "1" ]]; then
    "$PYTHON" "$ROOT/install_baton_desktop_mcp.py"
fi
# The .deb provides a system desktop entry. Existing user launchers must
# never be overwritten or prevent Baton startup.
if [[ "${BATON_INSTALL_SHORTCUT:-0}" == "1" ]]; then
    "$PYTHON" "$ROOT/install_baton_app.py"
fi
if [[ ! -x "$VENV/bin/python" ]]; then
    "$PYTHON" -m venv "$VENV"
fi
if ! "$VENV/bin/python" -c 'from PySide6.QtWidgets import QApplication' >/dev/null 2>&1; then
    "$VENV/bin/python" -m pip install --disable-pip-version-check 'PySide6>=6.8,<6.12'
fi
# ChatGPT OAuth validates signed OpenID tokens using PyJWT + cryptography.
# Installing the pinned-major authentication dependency is separate from the
# user's protected account credentials and cannot authorize any account.
if ! "$VENV/bin/python" -c 'import jwt; from cryptography.hazmat.primitives.asymmetric import rsa' >/dev/null 2>&1; then
    "$VENV/bin/python" -m pip install --disable-pip-version-check 'PyJWT[crypto]>=2.10,<3'
fi
echo "Starting Baton desktop Core. Model-client MCP registration is optional."
if [[ "${BATON_REGISTER_MCP:-0}" == "1" ]]; then
    echo "MCP registration requested; verify tool availability in the target client."
fi
exec "$VENV/bin/python" "$ROOT/baton_core_window.py"
