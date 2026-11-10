# Baton Remote security branch (2026-11-10)

Scope: independent admission gate only. Does not invoke a browser, terminal, MCP tool, HTTP listener, or existing ChatGPT conversation. Separate from PR #4 UI controller.

## Protocol
Canonical ASCII JSON object with exact keys: version=1, sender, target, message_id, issued_at (Unix seconds), action=wake_request, payload_sha256. HMAC-SHA256 hex signature over canonical JSON. Keys are per-sender 32+ random bytes, provisioned locally outside GitHub and never committed. The digest binds an approved payload, but this gate does NOT verify payload bytes: downstream controller MUST compare bytes to the approved digest before submission.

## Security boundary
Explicit sender/target allowlists; 60-second freshness; persistent SQLite unique sender/message_id constraint and BEGIN IMMEDIATE transaction. Accepted means queued for review, NOT delivered. No automatic retry on uncertain UI submission. Keep PAUSE_UI_WRITES active. Any transport adapter must bind loopback by default, authenticate before processing, impose request-size limits and timeouts, and never expose arbitrary shell/path execution. For remote access use an independently authenticated SSH tunnel or equivalent rather than exposing an unauthenticated HTTP port. Never infer UI wake from this gate.

## Installation (not performed on Greg)
From repository root: `python3 -m unittest discover -s tests -p 'test_remote_envelope_gate.py' -v`.
Use a private writable directory for SQLite (0700 parent); verify no symlink or shared-writable ancestor before creating database. This implementation does NOT yet enforce safe database path ownership, so do not run it as a privileged service. Do not bind it to the network until transport and filesystem hardening are independently reviewed.

## Pending negative tests
True multiprocessing race, symlink/path traversal on DB path, HTTP network exposure, malformed frame limits, delivery uncertainty, UI restart and actual A→B→C remain unverified. This branch intentionally does not claim those tests pass. Desktop Commander remote monthly quota was exhausted at implementation time; no Greg installation or live UI interaction performed.
