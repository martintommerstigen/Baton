#!/usr/bin/env bash
# Local, reversible Baton setup. No credentials, browser automation or network listener.
set -euo pipefail
REPO_URL="https://github.com/martintommerstigen/Baton.git"
BRANCH="feature/evening-local-terminal-2026-11-10"
TARGET="${HOME}/.local/share/baton-evening"
if [[ -e "$TARGET" && ! -d "$TARGET/.git" ]]; then
  echo "Refusing to overwrite non-Git path: $TARGET" >&2
  exit 1
fi
if [[ ! -d "$TARGET/.git" ]]; then
  git clone --depth 1 --branch "$BRANCH" "$REPO_URL" "$TARGET"
else
  echo "Existing checkout found; verifying its origin and branch without pulling."
  origin="$(git -C "$TARGET" remote get-url origin)"
  current="$(git -C "$TARGET" branch --show-current)"
  if [[ "$origin" != "$REPO_URL" || "$current" != "$BRANCH" ]]; then
    echo "Refusing mismatched repository or branch." >&2
    exit 1
  fi
fi
cd "$TARGET"
python3 -m unittest -v test_baton_local_terminal.py
python3 baton_local_terminal.py identity --workspace "$TARGET"
python3 baton_local_terminal.py git-revision --workspace "$TARGET"
echo "Baton local terminal adapter verified. No server was started."
echo "NOTE: This does not connect this ChatGPT conversation to Greg."
