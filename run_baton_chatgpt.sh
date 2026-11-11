#!/usr/bin/env bash
# Launch Baton embedded ChatGPT using isolated Python dependencies.
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${BATON_PYTHON:-python3}"
VENV="${BATON_QT_VENV:-$HOME/.local/share/baton/qt-venv}"
if [[ "$(id -u)" -eq 0 ]]; then
  echo "Run as Greg's normal user, not root" >&2; exit 1
fi
if [[ -z "${DISPLAY:-}" && -z "${WAYLAND_DISPLAY:-}" ]]; then
  echo "A graphical KDE session is required (DISPLAY/WAYLAND_DISPLAY missing)" >&2
  exit 1
fi
if [[ ! -x "$VENV/bin/python" ]]; then
  "$PYTHON" -m venv "$VENV" || {
    echo "Python venv unavailable. On Ubuntu/Kubuntu install python3-venv." >&2
    exit 1
  }
fi
if ! "$VENV/bin/python" -c 'from PySide6.QtWebEngineWidgets import QWebEngineView; from PySide6.QtWebEngineCore import QWebEngineProfile' >/dev/null 2>&1; then
  echo "Installing Baton QtWebEngine into private virtual environment..."
  "$VENV/bin/python" -m pip install --disable-pip-version-check 'PySide6>=6.8,<6.12'
fi
"$VENV/bin/python" -c 'from PySide6.QtWebEngineWidgets import QWebEngineView; from PySide6.QtWebEngineCore import QWebEngineProfile' || {
 echo "Qt WebEngine import failed. Check missing system libraries or wheel compatibility." >&2; exit 1
}
exec "$VENV/bin/python" "$ROOT/baton_chatgpt_view.py" "$@"
