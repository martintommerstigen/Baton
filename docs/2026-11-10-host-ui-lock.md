# 2026-11-10: shared host lock for existing-chat UI controllers

**Scope:** offline concurrency correction only. No live A→B→C wake has been verified.

## Failure found

The two-hop runner previously acquired a nonblocking `flock` on a file derived from `--db`, while the single-hop runner did not acquire a host-wide UI lock at all. Two independently invoked controllers with different ledger paths could therefore both act on the same authenticated ChatGPT browser session. SQLite reservations protect only one ledger file; they do not serialize distinct databases. An assistant reply might then be incorrectly attributed to the wrong submission.

## Correction

- Added `wake_ui_lock.py` with a **single per-user, per-host advisory lock** at `~/.cache/baton/chatgpt-ui.lock`, independent of SQLite database paths.
- Both `run_chatgpt_wake.py` and `run_chatgpt_wake_chain.py` acquire it **before connecting to the existing browser** and hold it through their controlled UI observation and send attempts.
- Lock acquisition is nonblocking: a competing cooperating controller fails closed without sending. No queueing or automatic retry is introduced.
- The lock directory must be owned by the current user and not group/world writable; the lock file must be owned by the current user, regular, and private. `O_NOFOLLOW` rejects symlink targets.
- The file contains no credentials, conversation text, or identifiers. The kernel releases `flock` on process exit, including a crash.
- `test_wake_ui_lock.py` covers cross-process exclusion, release on exception, symlink rejection, insecure directory/file rejection, and AST inspection that both entrypoints acquire the shared lock.

## Limits

This is **cooperative** exclusion among Baton runners using the same OS user and host. It does not prevent a person, another automation, or another host from interacting with the browser. It does not prove the ChatGPT UI selectors, message ID visibility, or a live wake. The per-target durable SQLite states, `PAUSE_UI_WRITES`, payload digest, source-turn provenance, and no-auto-resend-on-uncertainty behavior remain unchanged.

The old Baton v0 loopback queue is not the Greg-local forum, and neither an SIWC model-worker reply nor a successful CI run is a reply from an existing ChatGPT conversation.

## Source and verification

Sources read: [Baton issue #3](https://github.com/martintommerstigen/Baton/issues/3), PR #4, `run_chatgpt_wake.py`, `run_chatgpt_wake_chain.py`, `wake_contract.py`, and `chatgpt_ui_driver.py`; GTRCM `research/newborn-learning-dna-2026-11-07/README.md` (NEI / ikke-NEI / JA) and its negative-results record. `martintommerstigen/RustWorld` was inaccessible via the connected GitHub account (404), so its contents were not inspected.

A standalone local Linux execution of the first five lock tests passed (5/5), followed by six tests including the entrypoint static check (6/6) against local stand-ins. GitHub Actions on the final branch commit must be checked separately; **these local tests are not a live UI test**.

Remote Desktop Commander reported `remote_calls_left_pct: 0` and Greg online. No remote command, Greg installation, browser UI send, or pause-switch modification was performed. No secrets were committed.

**Remaining external acceptance gate:** an authorized authenticated browser/controller able to send into and observe fresh assistant-turn IDs in three distinct **existing** ChatGPT conversations, with the A→B and B→C receipts bound to those exact conversations.
