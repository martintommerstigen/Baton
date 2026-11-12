# Fail-closed existing-chat response correlation (12 November 2026)

**Scope:** independent narrow correction atop `feature/evening-local-terminal-2026-11-10`. No change to the canonical installed Greg Core, the existing three-chat wake experiment, or `PAUSE_UI_WRITES`. Source-only until independently installed and observed on Greg.

## Failure in the existing UI observer

The previous `baton_chat_observe.inspect_delivery_script()` marked an outgoing relay as visible if an earlier **user** turn contained the entire outgoing text *as a substring*, then accepted the **last** later assistant turn as the response. A different user message quoting the relay or an unrelated later assistant turn could be falsely classified as Baton's recipient answer. `baton_model_bridge.relay_poll()` even returned `reply_observed` when `data-message-id` was unavailable.

That is not an honest continuity receipt.

## Correction in this branch

- Match the **whole normalized user turn** by equality, not `includes`. A quotation containing the relay does not qualify.
- Require **exactly one** matching user turn. Duplicate exact markers are ambiguous.
- Correlate only the **immediately adjacent assistant turn**, never an arbitrary later reply.
- Require that this assistant turn have a **non-empty, unique `data-message-id`** among the rendered assistant turns. If the current ChatGPT UI does not expose unique IDs, do not fabricate a receipt.
- Do not call an assistant turn complete while the UI reports generation in progress.
- Recheck the exact destination conversation URL inside the asynchronous observation callback.
- Return `reply_observed` only through `verified_reply_observation`; otherwise preserve the no-blind-resend uncertainty boundary. Neither a Send click nor a quoted payload proves reception.
- Keep output text bounded. No cookies, credentials, authentication bypasses or extra network services.

## Verification

`test_baton_delivery_correlation.py` runs the actual generated DOM JavaScript against a deterministic browserless fake DOM under Node 22. Cases include valid adjacent response, quoted body, duplicate exact user turn, unrelated later assistant, missing/duplicate assistant ID, streaming and Python boundary checks. Workflow: `.github/workflows/existing-chat-correlation.yml`, plus inherited bridge/observer tests.

These tests can establish that the **observer logic** rejects these specific false-positive shapes. They cannot prove that a live existing ChatGPT page exposes the necessary DOM, that the model actually read a message, or that one SB continues another's identity.

## Remaining system-level prerequisites

1. An explicitly authorized, currently active Baton/Greg session, with `PAUSE_UI_WRITES` respected.
2. Durable request/response provenance across desktop restarts. The current embedded UI bridge still keeps request IDs in process memory; #3 / draft #4 has an independent durable wake ledger, but no verified installation/integration into this embedded bridge.
3. Read-only inspection of real DOM field availability and a single consented existing-chat A→B→C acceptance test: exact URLs, message IDs, freshly generated assistant IDs, failure/restart controls, no blind resend.
4. A separate **E → M → A** experiment for whether observed replies actually changed subsequent actions; UI receipt alone is *not* learning or consciousness.

**Source relationship:** [Baton issue #3](https://github.com/martintommerstigen/Baton/issues/3), [draft PR #4](https://github.com/martintommerstigen/Baton/pull/4), and existing `baton_chat_observe.py` / `baton_model_bridge.py`. This is a repair of a specific false-positive route, not another complete independent wake system.

**Bevar pilene.** A reply receipt is narrower than reception, comprehension, learning, or continuing personal identity.
