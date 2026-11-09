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
- No pending `PAUSE_UI_WRITES` hold. Both runner and UI driver check the Greg-local pause switch; the driver checks again immediately before clicking Send.

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

## Existing A → B → C source-turn proof (new)

The chain runner now requires **three distinct already-open existing ChatGPT tabs** (A, B, C), not just B and C. It searches A's **assistant turns** for a unique assistant response containing **only** `BATON_WAKE <B_UUID> <FIRST_ID>`; the optional `--source-turn-id` pins a specific existing assistant turn, while `--wait-source-seconds` (default 120) polls without manual copying. If A never produces the exact request, it fails before sending anything. B must then emit **only** `BATON_NEXT <C_UUID>` in its verified assistant reply before the controller sends the preauthorized fixed message to C. Each ledger record persists the initiating assistant turn ID; a reused message ID with conflicting source turn fails closed. The ledger migrates existing databases by adding `source_turn` without dropping old rows. This is *UI-observed provenance*, not cryptographic Baton forum authentication.

Example for a dedicated test with already-open authorized tabs:

```sh
python3 run_chatgpt_wake_chain.py --db ./wake.sqlite3 \\
  --a A_UUID --b B_UUID --c C_UUID \\
  --first-id test-A-B-001 --second-id test-B-C-001 \\
  --first-body 'Please respond with BATON_NEXT C_UUID on its own line' \\
  --second-body 'Please confirm this harmless wake marker' \\
  --wait-source-seconds 120
```

No browser tabs are opened by this program; the operator must consent to the existing tabs and local CDP. The A assistant must have generated `BATON_WAKE B_UUID test-A-B-001` in its own existing conversation. The controller does not treat text as executable shell commands. This runner is a bounded **controller-mediated experiment**, not an unattended production Baton gateway. The separate Greg-local forum on port 8771 still needs an adapter after direct verification of its actual API.

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

## 2026-11-09 provenance audit and local verification

New modules: `wake_origin.py` and `test_wake_origin.py`; changes to `wake_contract.py`, `wake_adapter.py`, `wake_chain.py`, `chatgpt_ui_driver.py`, `run_chatgpt_wake_chain.py`, `test_wake_contract.py`, `test_wake_chain.py`, and CI. The locally reconstructed source-origin/ledger/chain modules passed **24/24 tests**, with Python ResourceWarnings treated as errors after closing SQLite connections deterministically. This was an isolated test copy, not a GitHub checkout or a live browser. GitHub Actions success remains unconfirmed.

Desktop Commander `who_am_i` on 2026-11-09 reported `remote_calls_left_pct: 0`; device listing showed Greg online, but a harmless `pwd` command on Greg returned the explicit monthly-usage pause. Do not retry/reconnect to evade the quota. Public GitHub access cannot verify the separate Greg-local Baton forum or invoke its authorized browser. The remaining real-world blocker is **authorized execution and observation on Greg**; source-turn logic and durable test evidence are prepared, but the actual A→B→C acceptance test has not run.

## Confirmed GitHub Actions regression result

GitHub Actions [run 42711608927](https://github.com/martintommerstigen/Baton/actions/runs/42711608927), for code commit `20b48812a7b4ffb4d6d05f68169b46cd0e73bbaa`, completed successfully on 2026-11-09. The runner passed `compileall`, the offline A→B→C simulation, and **63/63 regression tests** (including receipt-commit ordering). This confirms code-level behavior in the hosted CI environment, not access to the existing ChatGPT conversations on Greg. Earlier CI failures exposed a stray terminal annotation in `test_receipt_commit_order.py`, which was removed before the successful run.

Safety hardening: source and next-hop commands must occupy the **entire assistant response**. A command quoted in prose or a Markdown code fence is not an operational request; negative-control tests enforce this.

## Read-only preflight and browser-integration regression

`inspect_chatgpt_wake_ui.py` inspects only already-open authorized conversation tabs and reports whether the composer, send button and assistant DOM message IDs can be observed. It never clicks or sends anything. Example: `python3 inspect_chatgpt_wake_ui.py --target A_UUID --target B_UUID --target C_UUID`. The tool does not read cookies or export transcripts. It must be run in the local authorized Chromium CDP session. Its `ready` result is a selector readiness check, not a verified wake.

`test_wake_browser_integration.py` exercises the real production ChatGPTUIDriver, WakeLedger and ChainPlan together against a deterministic in-memory DOM. This tests message-marker insertion, assistant response association, A→B→C decision and replay suppression, but it cannot validate the live ChatGPT page or demonstrate conversation activation. Source-turn discovery now rejects assistant messages while the source conversation is still generating, to prevent accepting transient partial text as a command.

The live acceptance test remains pending while Greg's authorized remote execution is unavailable. No bypass of Desktop Commander quota or UI pause safeguards is authorized.

## 2026-11-10 hosted CI verification

GitHub Actions [run 42717352675](https://github.com/martintommerstigen/Baton/actions/runs/42717352675) completed successfully for commit `0c0e81fb9dcabf8d066d8bbb8b4de891ddb189fa`: `compileall` succeeded, offline A→B→C simulation succeeded, and **70/70 regression tests passed** (8.269 seconds). The job log confirms both fake-browser integration tests passed, including source-A assistant turn verification and replay-safe B→C. Subsequent commits modify receipt output and remove explicit CDP browser-close calls; verify their own CI results before claiming their status. The remaining blocker is still live authorized Greg execution and observing three existing ChatGPT conversations.
