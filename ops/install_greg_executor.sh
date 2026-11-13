#!/usr/bin/env bash
# Install Baton Greg executor as a user service, not as root.
set -euo pipefail
if [[ "$(id -u)" == 0 ]]; then echo "Run as the Greg desktop user, not root" >&2; exit 2; fi
if [[ $# -ne 2 ]]; then echo "Usage: $0 CALLER_USERNAME SHARED_GROUP" >&2; exit 2; fi
caller="$1"; group="$2"
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
caller_uid="$(id -u "$caller")"
owner_uid="$(id -u)"
if [[ "$caller_uid" -eq 0 || "$caller_uid" -eq "$owner_uid" ]]; then
  echo "Caller must be a distinct non-root user" >&2; exit 2
fi
if ! id -nG "$caller" | tr ' ' '\n' | grep -Fxq "$group"; then
  echo "Caller must already belong to group $group" >&2; exit 2
fi
if ! id -nG | tr ' ' '\n' | grep -Fxq "$group"; then
  echo "Executor owner must already belong to group $group" >&2; exit 2
fi
runtime="$HOME/.local/share/baton-greg"
if [[ -e "$runtime" ]]; then
  [[ ! -L "$runtime" ]] || { echo "Refusing symlink runtime" >&2; exit 2; }
  [[ "$(stat -c %u "$runtime")" == "$owner_uid" ]] || { echo "Wrong runtime owner" >&2; exit 2; }
fi
install -d -m 0710 "$runtime"
chgrp "$group" "$runtime"
chmod 0710 "$runtime"
socket="$runtime/exec.sock"
if [[ -e "$socket" || -L "$socket" ]]; then
  echo "Existing socket. Stop service and inspect before replacing: $socket" >&2; exit 2
fi
service_dir="$HOME/.config/systemd/user"
install -d -m 0700 "$service_dir"
service="$service_dir/baton-greg-executor.service"
if [[ -e "$service" ]]; then echo "Service already exists; refusing overwrite" >&2; exit 2; fi
python="$(command -v python3)"
cat > "$service" <<EOF
[Unit]
Description=Baton native Greg execution broker
After=default.target

[Service]
Type=simple
WorkingDirectory=$repo
ExecStart=$python -m remote_security.greg_executor --socket $socket --allowed-uid $caller_uid --group $group --workdir $HOME
Restart=no
UMask=0117
NoNewPrivileges=yes

[Install]
WantedBy=default.target
EOF
systemctl --user daemon-reload
systemctl --user enable --now baton-greg-executor.service
echo "Installed: $service"
echo "Socket: $socket"
echo "Only local UID $caller_uid can request execution."
echo "WARNING: This grants the caller the same file write authority as $(id -un)."
echo "ChatGPT authorization and remote Baton routing are NOT installed by this script."
