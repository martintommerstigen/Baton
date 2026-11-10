# B1/B5 cross-branch interface contract — proposed, NOT implemented

Date: 2026-11-10. Process: Ronja (session-bound ChatGPT implementation run).
Source discussion: [B1 broker PR #16](https://github.com/martintommerstigen/Baton/pull/16),
[issue #3](https://github.com/martintommerstigen/Baton/issues/3),
[forum #6](https://github.com/martintommerstigen/Baton/issues/6).
Task IDs: B5/B2 -> B1. Evidence class: **design / implemented-unverified**;
no Greg installation, browser click, or existing-chat wake is asserted.

## NEG: SO_PEERCRED authenticates a local process, not an assistant turn

The B1 prototype's `SO_PEERCRED` establishes the kernel UID/PID/GID of the
socket peer. It does not establish that the peer's JSON `sender_id` corresponds
to an assistant turn in an existing ChatGPT conversation. A same-UID caller can
claim B->C without B ever generating `BATON_NEXT`. This is already a
documented negative test in PR #16; do not reinterpret `admitted` as
`delivered`, `source_complete` or `verified_turn`.

## Minimal UI/ledger integration boundary

1. **Trusted origin observation.** A separate read-only witness must observe
   the exact existing source conversation URL, a fresh unique assistant
   `data-message-id`, and the allowlisted `BATON_WAKE` or `BATON_NEXT`
   command. Bind source ID, observed turn ID, target ID, stable message ID,
   SHA-256 of approved UTF-8 payload, and observer identity into a durable
   attempt record. User-supplied `sender_id` is not a witness.
2. **Admission is not delivery.** The broker may grant one attempt for one
   target. It must not infer click success from a request, TLS/HTTP receipt,
   broker acknowledgement, timer, lease expiry, or UI-worker exit.
3. **Durable click boundary.** Before a trusted UI worker invokes a send
   button, atomically record `click_started` (or `uncertain`) and fsync.
   Hold the broker's per-conversation exclusion through final pause check,
   exact composer readback and click. If the UI worker can bypass this broker
   and click directly, the guarantee is only **cooperative**, not a
   security boundary against that worker.
4. **Crash and timeout.** If the worker crashes after `click_started`, or
   click outcome is not independently observed, preserve `uncertain` across
   process restart. Never authorize a second click automatically, even with
   the same message ID. Read-only reconciliation is permitted.
5. **Verification.** Only an independent observation of the same existing
   target URL, unique exact marker + approved body digest, and fresh unique
   assistant turn ID may promote an attempt to `verified_turn`. A B->C
   authorization requires the verified B assistant turn to contain the
   approved next-hop command, not a claimed JSON field.
6. **Pause.** PAUSE_UI_WRITES remains authoritative and fail-closed. A
   cooperative pause writer receives a successful acknowledgement only after
   the broker has durably stopped *future* admissions. An already started
   click cannot be retroactively cancelled.

## Falsifiers to implement in B1-owned tests

- Kill the UI worker immediately **after** durable `click_started`, before
  actual click: restart must remain uncertain; no second click.
- Kill it immediately **after** click, before target DOM observation:
  restart must remain uncertain; no automatic resend.
- Forge a B->C request from a same-UID client with no verified B turn:
  reject even if `SO_PEERCRED` succeeds.
- Forge a matching marker with wrong body digest or duplicate assistant
  `data-message-id`: no `verified_turn`.
- Race pause with pre-click and click: no click after a durably acknowledged
  pause; a pause request that loses to an already-started click must report
  that limitation rather than claim cancellation.
- Restart the broker between any two state writes: durable state must
  never move backward or make a second send admissible.
- Run a same-UID bypass process that clicks without broker admission: if
  possible, explicitly label the exclusion guarantee *cooperative*.
  A separate UID by itself does not grant exclusive access to the already
  authenticated browser session.

No change to B1 files, production pause state, project-map register, or
GTRCM/RustWorld canonical sources is proposed here. The independent B5
transport remains receive-only; it must not be treated as an UI executor.
