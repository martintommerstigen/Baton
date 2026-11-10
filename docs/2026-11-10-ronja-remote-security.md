# Baton Remote B5/B2 — Ronja independent security branch, second pass

Source: Baton issue #3 (existing-chat A→B→C acceptance), PR #4 (wake ledger/driver), draft PR #7 (read-only loopback gateway), project-map B5/B2, forum #6, GTRCM METHOD and RustWorld source-history README. This is an independent security gate, not a ChatGPT session identity or an existing-chat wake.

## Implemented

- Exact v1 canonical JSON envelope, per-sender HMAC-SHA256, sender/target allowlists, 60-second freshness, SQLite replay/collision receipts. The receipt state accepted_not_delivered is the ONLY positive state; it never asserts delivery.
- New accept_payload validates actual bytes (max 64 KiB) against the signed SHA-256 before durable acceptance. Legacy accept authenticates the envelope alone and MUST NOT be interpreted as verified payload. No execution of payload content.
- Private SQLite path guard: absolute non-normalized paths only, no symlink components, owner-only parent directory (0700), owner-owned regular database (0600), no hardlinks, no shared-writable ancestors except root-owned sticky ancestors such as /tmp. SQLite transactions now use a fresh connection per call; BEGIN IMMEDIATE serializes independent threads/processes. Existing Gate.db remains for compatibility.
- Local pause_guard uses lstat: an existing or dangling-symlink PAUSE_UI_WRITES marker is a pause. It returns no reusable send permit. A transport status cannot authorize a UI click.
- Negative tests: wrong payload before reservation, oversized/non-bytes payload, symlink DB and ancestor, traversal/relative paths, world-writable parent, loose file mode/hardlinks, 12-thread and 8-process duplicate race, restart/replay, malformed action, pause inserted after earlier status, dangling pause symlink.

## Installation (NOT performed on Greg)

Linux unprivileged dedicated account; Python 3.10+. Never run as root. Keep a private, owner-only directory for the database. For example, after reviewing a local checkout:

    umask 077
    install -d -m 700 "$HOME/.local/state/baton-remote"
    python3 -W error::ResourceWarning -m unittest discover -s tests -p 'test_*.py' -v
    python3 -m compileall -q remote_security tests

Keys: independently provision >=32 cryptographically random bytes per sender through owner-only local files or a separately reviewed secrets manager; no secrets in GitHub, shell arguments, CI, or documentation. The gate accepts key bytes in memory but does NOT implement key provisioning/rotation or network transport. A later HTTP/MCP adapter must authenticate, bound frames, enforce strict target policy and use a loopback listener plus SSH forwarding. The existing PR #7 gateway is read-only and does not call this gate.

## Security limits and falsifiers

- chatgpt_ui_driver.py in PR #4 uses PAUSE_FILE.exists() immediately before click. A dangling symlink returns False for .exists(), so that specific pre-click check is not fail-closed. This branch provides a tested lstat-based guard, but does not modify PR #4 (separate file ownership). A separately reviewed integration patch must replace that check and test the actual driver. A concurrent non-cooperating pause writer can still race between last check and click; an atomic guarantee requires a shared locking protocol.
- SQLite pathname checks are not an isolation boundary against malicious processes with the same UID. Run under a dedicated unprivileged UID, not as root. No Greg installation or remote reachability has been verified.
- No HTTP POST endpoint, MCP execution, SSH server, shell, UI sending, ChatGPT authentication, or network exposure is implemented here. This code must not be wired directly to an existing-chat UI without separate authorization, live target allowlists, pause recheck, and readback.
- True source-event completeness cannot be inferred from two agreeing transport receipts (Vanja R19). Nor does any accepted envelope prove a fresh assistant turn. Preserve the states implemented-unverified, tested-simulated, tested-live, and blocked separately.
- The old Baton v0 forum, SIWC worker, simulated A→B→C, and GitHub CI are not existing ChatGPT conversations. PAUSE_UI_WRITES and no blind retry remain binding.

Next test: review a small, independently authorized PR #4 adapter integration using lstat plus pre-click checks and test the pause marker inserted after health check. Test on Greg only after authenticated controller access and explicit authorization. Never promote a transport receipt to a wake receipt.

Evidence: local isolated Python tests and GitHub Actions results should be recorded separately. No claims of live Greg or A→B→C.
