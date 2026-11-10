# B1/B5 — durable pre-click uncertainty (2026-11-10)

**Status:** implemented, GitHub CI pending at authoring time; offline simulated tests only. No Greg deployment and **no existing-ChatGPT A→B→C verification**. Builds on [PR #16](https://github.com/martintommerstigen/Baton/pull/16), follows [issue #3](https://github.com/martintommerstigen/Baton/issues/3) and [Ronja's boundary contract](https://github.com/martintommerstigen/Baton/issues/6#issuecomment-6770468619).

## Contract

The local Unix-socket broker now accepts `begin_click` **only** when an exact five-field envelope is already durably admitted for an allowlisted target and the sticky pause / on-disk pause marker do not forbid the operation. The broker uses SQLite `BEGIN IMMEDIATE`, changes `admitted` to `uncertain`, commits, then returns `click_started_uncertain`. A second `begin_click` or `admit` for the same conversation is denied even after restart. The operation is deliberately one-way; no automatic retry or lease-based reopening exists.

`click_started_uncertain` is **not** a receipt, **not** evidence that the browser was clicked, and **not** proof that a ChatGPT assistant responded. A crash immediately after commit but before the click must remain uncertain; so must a crash after a click but before independent observation. This is conservative and may require human reconciliation.

## What this does not solve

- The UI worker is **not integrated** with this broker. Nothing prevents an uncooperative worker from clicking without `begin_click`. No live UI critical section is established.
- A `pause` committed after `begin_click` does not revoke the prior admission or prevent a later click; a trusted execution boundary and explicit pause ordering are still needed.
- Kernel `SO_PEERCRED` authenticates the connecting Unix UID, not the JSON `sender_id`, `origin_turn_id`, or a ChatGPT turn. Same-UID forged B→C remains a known negative control.
- SQLite serialization is not a security boundary against a process with permission to replace the DB or impersonate the trusted UI worker. A dedicated service UID and private state are deployment requirements, not current facts.
- The source and completeness of observed DOM evidence are not attested. GTRCM's source/witness distinction applies: a signed downstream log cannot establish an unseen upstream event by itself.

## Negative tests

`test_wake_admission_broker.py` now includes:
1. `begin_click` without prior admission rejected.
2. Changed message, sender, origin or payload digest rejected.
3. Repeated click-start and second admission denied.
4. Restart preserves uncertainty; no retry.
5. Pause before click-start blocks transition.
6. Concurrent click-start permits exactly one transition.
7. Pause after click-start does not falsely revoke the uncertain attempt.

Tests do not use Greg, browser sessions, tokens, or production pause files.

## Next falsifiable integration test

Introduce a dedicated trusted UI executor that calls `begin_click` and **waits for its committed response before any UI action**. Kill it (a) immediately after committed begin, before click, and (b) after click, before observation. In both cases restart must refuse a second click. Then require independent observation of a unique new assistant turn in the same pre-existing B conversation and a verifiable `BATON_NEXT` authored there before any C admission. Include wrong URL, reused turn ID, changed digest, and pause/click race negatives. Never promote a simulated ledger entry into `tested-live`.

## Provenance

- B1/B5 [project map](https://github.com/martintommerstigen/Baton/blob/planning/cross-project-map-2026-11-10/PROJECT_MAP.md)
- [GTRCM METHOD](https://github.com/martintommerstigen/GTRCM/blob/main/METHOD.md): do not promote a useful representation into ontology.
- [RustWorld README](https://github.com/martintommerstigen/GTRCM/blob/RustWorld/README.md): archived program variants are not live tests.
