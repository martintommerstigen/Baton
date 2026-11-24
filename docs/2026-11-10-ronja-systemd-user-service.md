# B5/B2 — optional Baton Remote systemd user service (2026-11-10)

**Status: implemented-unverified on Greg.** The unit file is a *template*, not an installation or authorization to run a service. A standalone `systemd-analyze verify` of its exact unit text passed in an isolated Linux container; this is syntax verification, not proof that Greg's user manager supports every sandbox directive.

Source: [Baton issue #3](https://github.com/martintommerstigen/Baton/issues/3), [PR #4](https://github.com/martintommerstigen/Baton/pull/4), [Ronja PR #8](https://github.com/martintommerstigen/Baton/pull/8), project-map B5/B2 and GTRCM [METHOD.md](https://github.com/martintommerstigen/GTRCM/blob/main/METHOD.md). This service only admits signed payloads to a private SQLite receipt store; it **does not** drive the ChatGPT UI or produce an existing-chat wake.

## Security contract

- Run as a dedicated **unprivileged** user, never a system/root service. Its home must be owner-controlled. The code must be reviewed locally before installation.
- Bind only `127.0.0.1:8788`; no LAN/WAN listener. An SSH tunnel, if separately approved, terminates on loopback. Do not open a firewall port.
- Keep the sender HMAC key, bearer token and database under owner-only directories and files. No credentials in GitHub, environment variables, command-line values, logs or screenshots. The command line includes **paths** to key files, not key bytes.
- Explicit `--route SENDER=TARGET` is mandatory. One sender's key must not authorize a different sender's target.
- `Restart=on-failure` restarts the **receiver only**, not a client request. There is no queue resend or replay after restart. `StartLimitBurst=3` bounds rapid crash loops.
- `NoNewPrivileges`, `UMask=0077`, `ProtectSystem=strict`, `ProtectHome=read-only` and a narrow `ReadWritePaths` constrain service effects. These controls do not isolate a malicious process with the same UID and must be checked against the actual user manager.
- `PAUSE_UI_WRITES` is never modified or interpreted as a permission to click. UI sending remains a separate, explicitly authorized controller concern.

## Local opt-in installation procedure (not executed)

1. Prepare a reviewed checkout of this exact Baton branch under the service user's home as `~/Baton`, or edit `WorkingDirectory` to the real checkout. Do not install unreviewed remote code.
2. Under that user, create `~/.config/baton-remote` and `~/.local/state/baton-remote` with mode 0700; generate separate random sender and bearer files with mode 0600 as documented in `docs/2026-11-10-ronja-remote-security.md`. Use a unique key per sender. Never use sample key bytes.
3. Edit the template's `sender000`, `target000`, `--route`, key paths and port to the actual authorized allowlist. No wildcard routes. Confirm the service's filesystem sandbox permits only the intended state directory.
4. Before any start, run the test suite and `systemd-analyze verify deploy/systemd/baton-remote-ingress.service`. A syntax pass does not verify the effective security boundary.
5. Only after local authorization, copy the reviewed unit into `~/.config/systemd/user/baton-remote-ingress.service`, run `systemctl --user daemon-reload`, then **manually** `systemctl --user start baton-remote-ingress.service`. Do not enable automatic login persistence or linger as part of this experiment.
6. Inspect `systemctl --user status baton-remote-ingress.service`, `ss -ltn` (must show only `127.0.0.1:8788` for this service), and run a harmless signed test with a fresh stable ID. After an ambiguous response, use the read-only receipt audit; never blind-retry.
7. Stop with `systemctl --user stop baton-remote-ingress.service` when not needed. No user service was installed or started by this work.

The unit's `ProtectHome` and `ReadWritePaths` interaction must be validated on Greg; a service that fails to start under confinement should remain stopped, not silently have its sandbox removed. No SSH forwarding, MCP integration or remote key rotation is claimed.

## Reproducible failure boundaries

`tests/test_remote_route_policy.py` checks that a sender with a valid HMAC key cannot address a target outside its exact route. `tests/test_http_process_crash.py` kills a disposable receiver before and after SQLite COMMIT. Both an absent receipt and a present authenticated receipt have `send_permitted=false`; the latter only proves local admission. `tests/test_remote_service_manifest.py` checks static unit invariants, not runtime confinement.

**Next live test:** with an authorized Greg session and remaining remote quota, verify effective user service sandbox, process restart, loopback-only binding, per-sender route rejection and read-only audit after a deliberately uncertain local request. Only then consider a restricted SSH tunnel. A→B→C across existing ChatGPT conversations is a separate B1 acceptance test.
