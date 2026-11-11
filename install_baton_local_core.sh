#!/usr/bin/env bash
# One-time Greg installation. No sudo, no remote command relay.
set -euo pipefail
if [[ "$(id -u)" == 0 ]]; then echo "Run as normal Greg user, not root" >&2; exit 1; fi
SOURCE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
TARGET="$HOME/.local/share/baton-core"
UNIT_DIR="$HOME/.config/systemd/user"
mkdir -p "$TARGET" "$UNIT_DIR"
chmod 700 "$TARGET"
for name in baton_exec_agent.py baton_local_api.py baton_mcp_stdio.py; do
  install -m 600 "$SOURCE_DIR/$name" "$TARGET/$name"
done
cat > "$UNIT_DIR/baton-local-api.service" <<EOF
[Unit]
Description=Baton local-only execution API
After=default.target

[Service]
Type=simple
WorkingDirectory=$TARGET
ExecStart=/usr/bin/python3 $TARGET/baton_local_api.py --port 52526
Restart=on-failure
RestartSec=5
NoNewPrivileges=yes
UMask=0077

[Install]
WantedBy=default.target
EOF
systemctl --user daemon-reload
systemctl --user enable --now baton-local-api.service
systemctl --user --no-pager status baton-local-api.service
printf '\nLocal API token: ~/.config/baton/local-api-token (never paste or commit)\n'
printf 'MCP host command: /usr/bin/python3 %s/baton_mcp_stdio.py\n' "$TARGET"
printf 'API binds only 127.0.0.1:52526; ChatGPT cloud cannot call it directly.\n'
