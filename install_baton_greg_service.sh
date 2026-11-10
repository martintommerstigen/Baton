#!/usr/bin/env bash
# Install the already-tested Baton private-GitHub mailbox as a user service.
# No inbound network listener; no secrets are printed or copied to GitHub.
set -euo pipefail
home="$HOME"
checkout="$home/.local/share/baton-evening"
key="$home/.ssh/baton_gtrcm"
service_dir="$home/.config/systemd/user"
service="$service_dir/baton-greg.service"
override="$service_dir/baton-greg.service.d/ssh.conf"

[[ -f "$checkout/baton_github_bus.py" ]] || { echo "Missing Baton checkout" >&2; exit 1; }
[[ -f "$key" && ! -L "$key" ]] || { echo "Missing Baton SSH private key" >&2; exit 1; }
[[ "$(stat -c %a "$key")" == "600" ]] || { echo "SSH key must have permissions 600" >&2; exit 1; }
command -v systemctl >/dev/null
mkdir -p "$service_dir" "$service_dir/baton-greg.service.d"
chmod 700 "$service_dir/baton-greg.service.d"
# SSH config avoids fragile systemd Environment= quoting and uses only this key.
ssh_dir="$home/.ssh"
mkdir -p "$ssh_dir"
chmod 700 "$ssh_dir"
config="$ssh_dir/config"
if [[ -L "$config" ]]; then echo "Refusing symlinked SSH config" >&2; exit 1; fi
# Use a dedicated alias so existing GitHub SSH configuration is left unchanged.
alias_name="github-baton-greg"
if [[ -f "$config" ]] && grep -Eq '^[[:space:]]*Host[[:space:]]+.*github-baton-greg([[:space:]]|$)' "$config"; then
  echo "Existing SSH alias github-baton-greg: refusing to overwrite" >&2
  exit 1
fi
cat >> "$config" <<EOF

Host github-baton-greg
    HostName github.com
    User git
    IdentityFile $key
    IdentitiesOnly yes
    BatchMode yes
EOF
chmod 600 "$config"
# Explicit GIT_SSH_COMMAND points at SSH alias config without nested quoting.
cat > "$service" <<EOF
[Unit]
Description=Baton private GitHub mailbox
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$checkout
Environment="GIT_SSH_COMMAND=ssh -F $config -i $key -o IdentitiesOnly=yes -o BatchMode=yes"
ExecStart=/usr/bin/python3 $checkout/baton_github_bus.py --transport ssh --loop --interval 20
Restart=on-failure
RestartSec=10
NoNewPrivileges=yes

[Install]
WantedBy=default.target
EOF
# Clean obsolete override from the previous manual setup.
rm -f "$override"
systemctl --user daemon-reload
systemctl --user enable --now baton-greg.service
systemctl --user restart baton-greg.service
systemctl --user --no-pager status baton-greg.service
echo "Baton user service installed; no inbound port opened."
