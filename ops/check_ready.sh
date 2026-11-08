#!/usr/bin/env bash
# Baton/Tailscale readiness checks. Does not install software or change network access.
set -euo pipefail
echo "Baton/Tailscale readiness (no secrets printed)"
echo "OS: $(. /etc/os-release; echo "$PRETTY_NAME")"
echo "Python: $(python3 --version)"
if command -v tailscale >/dev/null 2>&1; then
  echo "Tailscale: installed"
  tailscale status || true
  echo "Tailscale Serve:"
  tailscale serve status || true
else
  echo "Tailscale: NOT INSTALLED"
fi
if command -v ss >/dev/null 2>&1; then
  if ss -ltn '( sport = :8765 )' | grep -q '127.0.0.1:8765'; then
    echo "Baton: loopback listener present"
  else
    echo "Baton: loopback listener not found"
  fi
fi
echo "No credentials or network configuration changed."
