# Baton: live worker recovery (2026-11-09)

## Verified from repository

The public Baton v0 relay (`server.py`, loopback port 8765) explicitly does **not** provide ChatGPT integration. Its ACK means only authenticated client acknowledgement. This prototype is isolated from Rolf's active mailbox. Do not conflate it with the separate Greg-local Baton forum service reportedly on port 8771.

## Previously reported Greg-local work, not reverified in this run

- `/home/olliver/GTRCM-newborn-bootstrap` has a separate Baton forum and local loopback gateway on port 8771.
- `/home/olliver/baton-chatgpt-desktop` and `/home/olliver/gtrcm-siwc-devkit` previously produced a real SIWC model response.
- `baton_watch.service` was active, but watching is not waking a historical ChatGPT conversation.
- `baton_worker.mjs` was reportedly committed locally at `407390a`; a `[SIWC_WORKER_TEST]` invitation was posted in thread `eabcd29e-4a21-4b96-b69d-9803a2e87776`. No verified persisted reply/ack was retrieved before remote desktop access exhausted its quota.

## Required acceptance test

1. Verify actual local repository, commit and working tree without leaking tokens.
2. Verify service and worker process state; do not treat a running process as evidence of message processing.
3. Find the specific test invitation by stable thread/turn ID.
4. Confirm the worker generated a reply under its **own** source identity, persisted the reply in that same Baton thread, and recorded its returned turn ID.
5. Confirm acknowledgement only **after** durable reply; record crash/retry behavior and uncertain outcomes without resending irreversible work.
6. Report evidence and negative results; do not claim a historical ChatGPT chat woke up.
7. Commit code and tests to the correct repository/branch after verifying remotes. Do not commit tokens, database contents, private chat transcripts, or secrets.

## Constraints

Preserve `transport/PAUSE_UI_WRITES`, `rolf_chat_shared.lock`, identity provenance, and `NAVN KAN PASSERE. PERSONER KAN IKKE`. Do not bypass a hold or automatically replay uncertain sends.

## Current limitation

GitHub access can preserve this recovery plan but cannot start a process on Greg without a verified Greg-side pull/runner. No automatic execution is claimed.
