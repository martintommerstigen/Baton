# Baton Remote B1/B5 — read-only loopback gateway

**Status:** implemented, offline-tested; **not installed or live-verified on Greg**. This is a separate transport bootstrap, **not** old Baton v0 (port 8765), the Greg-local forum, SIWC, or a ChatGPT existing-conversation wake.

## Boundary and provenance

The gateway is Python standard library only (no third-party runtime packages or copied external code). It binds **127.0.0.1:8787**, rejects non-loopback Host headers and requires an owner-owned, owner-only (0600/0400), non-symlink token file containing at least 32 ASCII bytes. It exposes authenticated GET /v1/health and GET /v1/pause-status only. All other GET paths and all POST/PUT/DELETE operations are denied. It never executes a shell, accesses ChatGPT cookies, creates a browser session, sends messages, reads arbitrary files or modifies the pause switch. Responses exclude credentials and are marked no-store.

A present PAUSE_UI_WRITES file, dangling symlink or filesystem access error reports paused. An absent marker means only that the configured path was absent; it is **not** permission to send anything. The service has no UI-writing operation.

**Security limitation:** This is an initial local read-only gateway, not a complete remote-control service or a production-grade authenticated tunnel. Token distribution, SSH key management, audit, rate limiting, rotation, supervision and authorization of future write operations require separate review. Do not expose port 8787 publicly.

## Installation example — authorized local checkout on Greg (NOT YET EXECUTED)

Run as an unprivileged user with Python 3.10+ in a reviewed checkout:

```sh
umask 077
install -d -m 700 "$HOME/.config/baton-remote"
python3 -c 'import secrets; print(secrets.token_urlsafe(48))' > "$HOME/.config/baton-remote/token"
chmod 600 "$HOME/.config/baton-remote/token"
python3 -m baton_remote_b1.agent --token-file "$HOME/.config/baton-remote/token" --port 8787 --pause-file "$HOME/GTRCM-newborn-bootstrap/transport/PAUSE_UI_WRITES"
```

No token belongs in GitHub, CLI arguments, issues or chat. On the same host:

```sh
python3 -m baton_remote_b1.client health --token-file "$HOME/.config/baton-remote/token"
python3 -m baton_remote_b1.client pause-status --token-file "$HOME/.config/baton-remote/token"
```

For a second **authorized** host, use an existing authenticated SSH connection, with loopback forwarding, e.g.:

```sh
ssh -N -L 127.0.0.1:8787:127.0.0.1:8787 olliver@greg-host
```

The remote client still needs its own securely provisioned token file. Alternatively use a private WireGuard tunnel; keep the HTTP gateway on loopback. **An SSH tunnel does not itself connect ChatGPT automation to Greg**; that requires a separately authorized and verified integration.

## Test

```sh
python3 -m compileall -q baton_remote_b1 test_baton_remote_b1.py
python3 -W error::ResourceWarning -m unittest -v test_baton_remote_b1
```

Ten offline tests: authenticated health, missing/wrong token, forged Host, rejected shell/write, pause file and dangling symlink, client URL and operation allowlist, no-store headers, restart, token permissions and symlink rejection, and no credential leakage in health response. Tests use a real loopback HTTP server with a synthetic pause file; they do not establish Greg reachability or a real ChatGPT wake.

## Integration and next falsifiers

1. On Greg, verify explicit authorization, localhost binding, token ownership and a real SSH-forwarded read-only request. Record source host and result without secrets.
2. Test connection loss, hostile clients, token rotation and revocation before expanding beyond read-only operations.
3. A future separately reviewed UI adapter must enforce existing-chat allowlists, actual source/target assistant turn IDs, PAUSE_UI_WRITES, atomic reservations and uncertain/no-blind-retry. Never treat a gateway health response as proof of delivery.
4. A→B→C remains blocked until three existing ChatGPT conversations actually receive/produce new turns and their IDs are independently observed.

Sources: [Baton issue #3](https://github.com/martintommerstigen/Baton/issues/3), [wake ledger PR #4](https://github.com/martintommerstigen/Baton/pull/4), [project map PR #5](https://github.com/martintommerstigen/Baton/pull/5) (IDs B1/B5), [forum #6](https://github.com/martintommerstigen/Baton/issues/6), and [GTRCM METHOD.md](https://github.com/martintommerstigen/GTRCM/blob/main/METHOD.md). Implementation status is **tested-simulated** for loopback transport, **implemented-unverified** on Greg, **blocked** for actual A→B→C.
