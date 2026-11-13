#!/usr/bin/env bash
# Local, reversible Baton setup and safe update for the canonical Greg checkout.
set -euo pipefail
REPO_URL="https://github.com/martintommerstigen/Baton.git"
BRANCH="feature/evening-local-terminal-2026-11-10"
TARGET="${HOME}/.local/share/baton-evening"
SCRIPT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

if [[ -L "$TARGET" || ( -e "$TARGET" && ! -d "$TARGET/.git" ) ]]; then
  echo "Refusing to overwrite non-Git path: $TARGET" >&2
  exit 1
fi

if [[ ! -d "$TARGET/.git" ]]; then
  git clone --depth 1 --branch "$BRANCH" "$REPO_URL" "$TARGET"
else
  echo "Existing Baton checkout found; attempting safe fast-forward only."
  python3 "$SCRIPT_ROOT/baton_safe_update.py" \
    --checkout "$TARGET" --origin "$REPO_URL" --branch "$BRANCH"
fi

cd "$TARGET"
python3 desktop/preflight_greg.py
python3 -m unittest -v test_baton_local_terminal.py
python3 baton_local_terminal.py identity --workspace "$TARGET"
python3 baton_local_terminal.py git-revision --workspace "$TARGET"
echo "Baton checkout verified and current. No server was started."
echo "Run Baton from the desktop app, then use 'Koble denne chatten' in the browser extension."
