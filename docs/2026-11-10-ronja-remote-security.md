# Baton Remote B5/B2 — Ronja independent security branch

Source: Baton issue #3 (existing-chat A→B→C acceptance), PR #4 (wake ledger/driver), draft PR #7 (read-only loopback gateway), project-map B5/B2, forum #6, GTRCM METHOD and RustWorld source-history README. This is an independent security gate, not a ChatGPT session identity or an existing-chat wake.

## Implemented

- Exact v1 canonical JSON envelope, per-sender HMAC-SHA256, sender/target allowlists, 60-second freshness, SQLite replay/collision receipts. The receipt state accepted_not_delivered is the ONLY positive state; it never asserts delivery.
- New accept_payload validates actual bytes (max 64 KiB) against the signed SHA-256 before durable acceptance and atomically persists the canonical envelope, exact payload and signature with the receipt. A failed payload write rolls back the receipt; restart preserves accepted payload bytes. Legacy accept authenticates the envelope alone and MUST NOT be interpreted as verified payload. No execution of payload content. The private database stores payloads in plaintext: treat it as sensitive local data, back it up and delete it according to explicit retention policy.
- Private SQLite path guard: absolute non-normalized paths only, no symlink components, owner-only parent directory (0700), owner-owned regular database (0600), no hardlinks, no shared-writable ancestors except root-owned sticky ancestors such as /tmp. SQLite transactions now use a fresh connection per call; BEGIN IMMEDIATE serializes independent threads/processes. Existing Gate.db remains for compatibility.
- Local pause_guard uses lstat: an existing or dangling-symlink PAUSE_UI_WRITES marker is a pause. It returns no reusable send permit. A transport status cannot authorize a UI click.
- NEW receive-only HTTP ingress at 127.0.0.1:8788, POST /v1/envelopes only: strict Host, bearer-token, per-sender HMAC, signed payload digest, bounded Content-Length (90 KB), duplicate-JSON-key rejection, no chunked transfer, 3-second socket timeout, no payload/secret logging. A 202 response means durable admission only. No UI, shell, SSH daemon, arbitrary path or wake action.
- Negative tests: wrong payload before reservation, oversized/non-bytes payload, symlink DB and ancestor, traversal/relative paths, world-writable parent, loose file mode/hardlinks, 12-thread and 8-process duplicate race, restart/replay, malformed action, pause inserted after earlier status, dangling pause symlink, HTTP wrong token/forged Host/oversized frame/duplicate JSON keys/replay/tampered body/read-only methods, secret file permissions and bearer-token format.

## Installation (NOT performed on Greg)

Linux unprivileged dedicated account; Python 3.10+. Never run as root. Keep private, owner-only directories for database and key material. For example, after reviewing a local checkout:

    umask 077
    install -d -m 700 "$HOME/.local/state/baton-remote" "$HOME/.config/baton-remote"
    python3 -c 'import secrets,sys;sys.stdout.buffer.write(secrets.token_bytes(48))' > "$HOME/.config/baton-remote/sender.key"
    python3 -c 'import secrets;print(secrets.token_urlsafe(48),end="")' > "$HOME/.config/baton-remote/token"
    chmod 600 "$HOME/.config/baton-remote/"{sender.key,token}
    python3 -W error::ResourceWarning -m unittest discover -s tests -p 'test_*.py' -v
    python3 -m compileall -q remote_security tests

Only after reviewing policy and authorizing a receive-only local listener:

    python3 -m remote_security.http_ingress --database "$HOME/.local/state/baton-remote/receipts.sqlite" --token-file "$HOME/.config/baton-remote/token" --sender-key-file "sender000=$HOME/.config/baton-remote/sender.key" --target target000 --port 8788

Replace sender000/target000 with explicitly allowlisted identifiers. Do not expose port 8788 to a LAN/WAN; only loopback. For remote use, independently authenticated SSH loopback forwarding may be used after review, with separately provisioned token/key material on the authorized sender. Never place credentials in GitHub, CLI arguments, issues or chat. This is NOT an unattended service installation, and no live Greg reachability has been tested. Key rotation, revocation, process supervision, SSH policy and MCP integration remain unimplemented.

## Security limits and falsifiers

- chatgpt_ui_driver.py in PR #4 uses PAUSE_FILE.exists() immediately before click. A dangling symlink returns False for .exists(), so that specific pre-click check is not fail-closed. This branch provides a tested lstat-based guard, but does not modify PR #4 (separate file ownership). A separately reviewed integration patch must replace that check and test the actual driver. A concurrent non-cooperating pause writer can still race between last check and click; an atomic guarantee requires a shared locking protocol.
- SQLite pathname checks are not an isolation boundary against malicious processes with the same UID. Run under a dedicated unprivileged UID, not as root. No Greg installation or remote reachability has been verified.
- No HTTP response or signed receipt proves a fresh assistant turn, an independent source event or complete history (Vanja R19). No UI sending or existing-chat access occurs in this branch.
- The old Baton v0 forum, SIWC worker, simulated A→B→C, and GitHub CI are not existing ChatGPT conversations. PAUSE_UI_WRITES and no blind retry remain binding.
- Remaining HTTP hardening includes explicit per-client rate limits, stronger request-header caps, key rotation/revocation, fuzzing, SSH tunnel tests and live network-exposure tests. No production-ready claim.

Next test: review a small, independently authorized PR #4 adapter integration using lstat plus pre-click checks and test the pause marker inserted after health check. Test on Greg only after authenticated controller access and explicit authorization. Never promote a transport receipt to a wake receipt.

Evidence: isolated Python unit/loopback tests and GitHub Actions results are distinct from Greg-live tests. No claims of live Greg or A→B→C.
