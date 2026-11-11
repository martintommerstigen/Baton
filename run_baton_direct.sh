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
"$PYTHON" "$ROOT/install_baton_desktop_mcp.py"
"$PYTHON" "$ROOT/install_baton_app.py"
if [[ ! -x "$VENV/bin/python" ]]; then
    "$PYTHON" -m venv "$VENV"
fi
if ! "$VENV/bin/python" -c 'from PySide6.QtWidgets import QApplication' >/dev/null 2>&1; then
    "$VENV/bin/python" -m pip install --disable-pip-version-check 'PySide6>=6.8,<6.12'
fi
echo "Baton MCP configured. Keep this Core window open while using ChatGPT desktop."
echo "If official ChatGPT Linux desktop is installed, restart it and check Settings > MCP servers."
exec "$VENV/bin/python" "$ROOT/baton_core_window.py"
