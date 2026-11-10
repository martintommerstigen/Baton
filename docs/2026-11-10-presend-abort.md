# 2026-11-10: proven pre-click rejection vs uncertain post-click delivery

**Status: code-level correction verified; real existing-chat A→B→C NOT verified.**

## Concrete failure mode

Before this change, a wake reserved the recipient as `submitting` and then attempted to use the ChatGPT composer. If the user had an unsent draft, the Greg-local `PAUSE_UI_WRITES` switch appeared, the send button was disabled, or the composer changed the approved body, the UI driver rejected the operation **before clicking Send**. The adapter caught that rejection as a generic exception and persisted `uncertain`. An unrelated later wake to the same target was then blocked by the per-target exclusion until a receipt that could never exist was reconciled.

This is an important operational distinction: **proved no click** is neither **uncertain click** nor **verified reply**. Treating these as one state makes the target indefinitely unavailable after a harmless preflight rejection.

## Implemented

- Added typed `PreSubmissionRejected` to `wake_adapter.py`, reserved exclusively for UI preflight failures before `send.click()`.
- Added terminal `aborted` transition in `WakeLedger.mark_aborted`. Reconciliation never promotes it to `verified`; the same wake ID is never retried.
- ChatGPT UI preflight rejects a draft, missing composer, disabled send, pause switch, and composer/body mismatch using the typed exception. It **leaves the draft untouched/unsent**. The operator must clear the draft explicitly before a new message ID can be submitted.
- An error **after clicking Send** remains `uncertain`, blocks competing sends, and is eligible only for read-only reconciliation. The UI driver never emits `PreSubmissionRejected` after Send.
- Preexisting-marker collisions remain a separate terminal `collision`; no change to allowlist, source turn provenance, approved SHA-256 binding, pause behavior, or no-auto-resend rule.

## Regression evidence

Five tests added in `test_wake_presend_abort.py`: paused pre-click attempt; unsent user draft; mutated composer; post-click exception with no automatic replay and later read-only reconciliation; terminal aborted receipt cannot be verified. The synthetic second assistant reply uses a **fresh** turn ID to avoid a false collision.

CI first attempt [42774808103](https://github.com/martintommerstigen/Baton/actions/runs/42774808103) failed in two **test fixtures**, not in the new ledger behavior: the pause test incorrectly assumed the unsent draft would disappear, and the fake browser reused the same assistant turn ID for a second successful response. Both expectations were corrected without weakening the fail-closed checks.

Final GitHub Actions [run 42774879831](https://github.com/martintommerstigen/Baton/actions/runs/42774879831) on code commit `46d6b89019295f07ee8f040ff35a1183644063ea`:
- Python compilation: PASS.
- Offline A→B→C simulation: PASS (not live).
- **104/104** Python tests: PASS.
- The five new tests: PASS.

## Sources and external boundary

- [Baton issue #3](https://github.com/martintommerstigen/Baton/issues/3), `wake_adapter.py`, `wake_contract.py`, `chatgpt_ui_driver.py`, synthetic DOM integration and CI logs.
- GTRCM branch `research/newborn-learning-dna-2026-11-07`: `README.md` distinguishes `NEI`, `ikke-NEI`, `JA`; `NEGATIVE_RESULTS.md` records negative findings instead of promoting assumptions.
- `martintommerstigen/RustWorld/README.md` was inaccessible (GitHub 404 under the connected account); no claim to have read its source.
- Remote Desktop Commander `who_am_i` on 2026-11-10 reported `remote_calls_left_pct: 0`. No Greg terminal or UI write was attempted.
- GitHub Actions, old Baton v0, Greg-local forum and SIWC model workers are **not** evidence that a historical ChatGPT conversation was awakened.

**Single remaining external acceptance gate:** authorized authenticated browser/controller access that can submit into the specified existing ChatGPT A/B/C conversations and read distinct fresh assistant-turn IDs. Current selectors also require live validation within that gate. Do not claim completion before actual A→B→C receipts exist.
