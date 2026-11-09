# Existing-chat UI wake experiment (opt-in, not yet verified on Greg)

This branch adds an **actual browser-facing adapter**, not just a message queue:
`run_chatgpt_wake.py` → `wake_adapter.py` → `chatgpt_ui_driver.py`.
It uses a previously opened, logged-in ChatGPT conversation tab. It does not
create another model worker or a new conversation.

## Preconditions

- An authorized operator already opened the target existing ChatGPT conversation
  in Chromium, and deliberately enabled a **loopback-only** CDP endpoint.
- Python Playwright is installed on that same machine.
- The target UUID is explicitly allowlisted by the invocation.
- No user draft is present in the target composer.
- UI selectors are confirmed against the *current* ChatGPT interface.
- No pending `PAUSE_UI_WRITES` hold. This stand-alone proof-of-concept does **not**
  read that hold itself, so do not run it under a paused system.

CDP access can control the logged-in browser. **Never expose CDP to the network**
or use a personal browsing profile with unrelated sensitive tabs. Do not store
session cookies, tokens, or transcripts in GitHub.

## Local, explicitly authorized proof-of-concept

```sh
python -m pip install playwright
python run_chatgpt_wake.py --db ./wake.sqlite3 \
  --target EXISTING_TARGET_CONVERSATION_UUID \
  --source EXISTING_SOURCE_CONVERSATION_UUID \
  --id unique-test-message-id \
  --body 'Har du mottatt denne Baton-testen?'
```

This requires an *already running* Chromium exposing CDP on
`http://127.0.0.1:9222`; it will not start one. For a pending/uncertain attempt,
run the same command with `--reconcile` and omit `--source`/`--body`.
Reconciliation never submits again.

## Strict result interpretation

- `requested`: persisted only; no UI attempt.
- `submitting`: submission began; outcome unknown after crash.
- `uncertain`: submission attempted, no verified assistant turn.
- `verified`: UI adapter observed a matching user marker followed by a nonempty
  assistant DOM turn ID in the *same* existing conversation.
- No code here currently confirms semantic comprehension or that B independently
  requested and successfully woke C.

DOM selectors (`#prompt-textarea`, `data-message-author-role`,
`data-message-id`, `data-testid=stop-button`) are hypotheses requiring
validation on the current UI. If absent, the adapter must fail closed.
An assistant message ID may not be exposed in the DOM. Do not invent one.

## Remaining acceptance work

1. Verify real UI selectors on Greg without sending a message.
2. Add a verified send confirmation and wait for completed response; distinguish
   typing from submission and avoid interpreting stale turns as replies.
3. Respect `PAUSE_UI_WRITES` in the runner and prevent simultaneous writers.
4. Verify a real A→B wake with persisted UI evidence.
5. Design a narrowly authorized B→C request protocol and verify B→C in a
   separate existing conversation. No automatic execution of arbitrary model text.
6. Integrate with the **correct** Greg-local Baton forum; do not confuse it with
   this repository's older v0 relay on port 8765.

## Critical provenance limitation (2026-11-09 audit)

The current --source/--a CLI values are caller assertions, not proof that existing conversation A initiated anything. A successful UI submission to B proves only controller-initiated wake of B. Even if B requests C and the controller sends to C, this is not yet strict autonomous A-to-B-to-C.

A production integration must consume a provenance-correct event from the authorized execution context of existing conversation A, bind it to the actual chat ID, and preserve the source evidence. Never infer origin from copied text or arbitrary source labels.

## Audit corrections

The initial UI driver had malformed duplicated source and was repaired. Offline ledger/chain simulation passed in an isolated local reconstruction: two unique sends, zero replay sends. Six fake-DOM tests and a concurrent SQLite verification check passed locally. These are not real browser wake tests. CI now includes compileall, simulation and regression tests, but no successful GitHub Actions run is yet confirmed.
