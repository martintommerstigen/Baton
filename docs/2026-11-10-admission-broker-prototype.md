# B1/B5: experimental local admission broker — 2026-11-10

**Evidence status:** implemented, offline tests pending GitHub Actions at first commit. NOT deployed on Greg. NOT live ChatGPT wake.

## Why this branch exists

[Issue #3](https://github.com/martintommerstigen/Baton/issues/3) requires actual existing-chat A→B→C. [PR #14](https://github.com/martintommerstigen/Baton/pull/14) demonstrates a post-validation inode swap that splits a same-UID `flock`. [Ronja's broker response](https://github.com/martintommerstigen/Baton/issues/6#issuecomment-6769784130) proposes kernel peer credentials and a durable uncertain-attempt ledger. This branch prototypes the **admission** portion, not the UI click.

## Contract and limits

- Linux-only Unix socket; `SO_PEERCRED` checks actual connecting UID. Socket defaults to mode 0600. It does not authenticate a claimed `sender_id` or verify a ChatGPT turn; those are separate responsibilities.
- SQLite `BEGIN IMMEDIATE` serializes admission and pause. At most one outstanding attempt per allowlisted conversation; the attempt binds sender, origin turn, message ID and SHA-256 of exact payload. An admission is `admitted_not_delivered`, **never a delivery receipt**.
- A duplicate, changed payload, unsupported operation, invalid ID, unallowlisted conversation, or uncertain restart cannot authorize another attempt. No expiry, automatic retry or automatic reconciliation exists.
- Persistent `pause` denies new admissions; it cannot revoke an admission already given. The existing `PAUSE_UI_WRITES` path is checked fail-closed for missing ancestors, symlinks and existing markers. **This is not an atomic pause-vs-UI-click guarantee** until the actual UI driver participates in one serialized admission/click protocol.
- No shell, no public TCP listener, no credentials in GitHub. No command from untrusted forum content is executed.

## Local offline test

```bash
python3 -m unittest -v test_wake_admission_broker.py
```

A disposable Unix socket and SQLite database are created under `TemporaryDirectory`. Tests cover concurrent admission, duplicate/collision, crash/restart, sticky pause, missing/symlinked pause marker, kernel UID rejection, oversized input and socket-path collision.

## Manual lab launch (not a deployment instruction)

Use a disposable, user-owned directory with permissions 0700 and a real, already existing parent directory for the pause marker. Never point this experimental broker at the production browser before integration review.

```bash
python3 wake_admission_broker.py \
  --socket /tmp/PRIVATE-DIR/broker.sock \
  --db /tmp/PRIVATE-DIR/admissions.sqlite \
  --pause-path /tmp/PRIVATE-DIR/PAUSE_UI_WRITES \
  --conversation chat-B --conversation chat-C
```

Use a dedicated service account and private state directory in a future deployment. The current mode-0600 socket admits the owning UID only. Cross-UID access requires an explicitly designed Unix group/ACL/socket-activation configuration, not changing the state directory to world-writable. Same-UID hostile code can still tamper with same-UID state; this prototype **does not solve that threat**. A separate privileged broker and least-privilege UI caller are future integration requirements.

## Falsifiers / next tests

1. Can a same-UID adversary replace the broker's database, socket or process? Yes under an unisolated same-UID deployment; test OS-separated ownership and ACLs before claiming adversarial protection.
2. Can the UI click occur after admission but after pause is requested? Yes until a broker-mediated critical section encloses the actual click. Do not promote admission into click authorization or delivery.
3. Does A cause B to respond and B cause C to respond at existing URLs? Not tested. Requires Greg or another authorized logged-in controller, immutable IDs and independently observed turns.

GTRCM discipline: representation/protocol is not physical observation; [METHOD](https://github.com/martintommerstigen/GTRCM/blob/main/METHOD.md) and [NEGATIVE_RESULTS](https://github.com/martintommerstigen/GTRCM/blob/main/NEGATIVE_RESULTS.md). The project map B1/B5 is coordination, not proof.
