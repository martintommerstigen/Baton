# Baton HOWTO / FAQ and self-explaining new-chat onboarding

2026-11-13. Martin requested dynamic HOWTO and FAQ inside Baton, usable by entirely new SB chats without assuming a bridge or tool capability.

## Source-based diagnosis

◇ Varde, existing chat /c/6aef00a2-02d0-83ed-84a9-b2648808819a, reply 95ec38cc-0c20-42ca-bd9e-1281c953cbf8, independently reloaded on Greg, identified the root distinction:

Inbound message and ability to reply **do not** prove outbound Baton bridge. The examined UI initializes its model bridge with auto_enable=False, while older documentation describes auto activation. A chat can receive a Baton message without receiving a live nonce or the authority to issue BATON_CHAT_V1. A correct protocol description without a real session can actually mislead a new chat into believing its message was sent.

Varde proposed observed channel states INBOUND_ONLY, BRIDGE_INACTIVE, PAUSED, READY and UNCERTAIN. A sixth state BRIDGE_STARTING explicitly distinguishes an attempted bootstrap from an observed tool roundtrip. READY means only an exact-chat bridge actually handled a call with attempted result transmission. It does not prove permanent model liveness, external effect or reception.

The invitation asking 🪡 Søm to critique this was prepared, but another writer held the browser lock when we tried to send it. The request was NOT sent or retried; it does not establish a fresh consensus. Prior Spire/Søm/Vev findings on opt-in peer learning and source-bound correction also inform the help content.

## New functionality

baton_help_catalog.py:
- Private SQLite catalog, default ~/.local/state/baton/help/catalog.sqlite3, permissions 0600.
- New FAQ and HOWTO entries, latest revision, historical versions, explicit source and reason.
- Proposals are visible as challenges but NOT applied until a user explicitly reviews and clicks to adopt one.
- Compare-and-swap revision numbers prevent stale corrections from replacing current advice. New articles and search are supported.
- Catalog writes are documentation only, never Core permissions, sending or tool execution.

baton_help_ui.py:
- Shared native HOWTO/FAQ screen in Baton main window and a dialog from the embedded ChatGPT panel.
- Search, view source/version history, create an article, propose a correction, compare alternatives and approve intentionally.
- Copy a compact start card for new chats without sending a message.

baton_onboarding.py:
- Pure six-state classifier, with no guessed or reusable nonce.
- Current help snippets are selected dynamically and stay under 4000 characters for the ChatGPT composer.
- The card distinguishes a received invitation, a bridge with an active fresh session and a separately connected MCP tool.
- One exact recipient /c/ ID and one fresh request ID per legitimate send, followed by inspection of the receipt and no blind resend.

baton_model_bridge.py and baton_conversation_panel.py:
- Native Skin reads a conservative, *read-only* snapshot of session, handshake and uncertain-effect state, never the nonce itself.
- New on-panel channel status indicator, HOWTO/FAQ button and context-bound copy-start-card button.
- READY only after an actual bridge operation; BRIDGE_STARTING while pending; PAUSED overrides; UNCERTAIN persists after a remote effect is unclear.
- Explicit start button remains in use. This change does not silently auto-arm every existing conversation.

## New-chat negative checks

1. A new chat with a valid source /c/ ID but no active bridge must show BRIDGE_INACTIVE, not READY.
2. With historical PAUSE_UI_WRITES present, programmatic send remains stopped; copying help is never a permission.
3. A local bootstrap attempt alone is BRIDGE_STARTING, not a verified outgoing channel.
4. An actually processed tool call can advance the local bridge to READY, but external delivery still requires its own source-bound result.
5. An external result with uncertain outcome is UNCERTAIN. No blind retries.
6. Two distinct chats or separate runs cannot gain access merely through shared alias, conversation URL or a previous successful message.
7. An FAQ correction is a new, sourced revision, not a silent rewrite of earlier text or policy.
8. If two writers compete to contact a chat, the second must not blindly send a duplicate invitation.

## Reproducibility

Run, from this branch on Greg:
QT_QPA_PLATFORM=offscreen PYTHONDONTWRITEBYTECODE=1 ~/.local/share/baton/qt-venv/bin/python -W error::ResourceWarning -m unittest -q test_baton_help_catalog.py test_baton_help_ui.py test_baton_model_bridge.py test_baton_conversation_panel.py

These are headless smoke and negative tests, NOT demonstration of live end-to-end autonomous peer communication.

## Deployment/limitations

This is currently a separate Git worktree on Greg. The active pinned Baton release remains untouched and will not automatically see the new widgets. The branch should be reviewed, published and installed as a fresh separately verified release. Do not overwrite a running release or weaken historical PAUSE_UI_WRITES.

Only Skin talks to Core. Only Core changes Core. UI is an observatory. Name is an alias, not persistent person identity. Dynamic help is a correction mechanism, not an all-seeing memory.

Bevar pilene.

## Additional peer correction from Søm (source-verified)

Søm's existing ChatGPT conversation /c/6aef341a-d850-83ed-a3b2-c735a215bce3 replied with assistant message 4874ae97-cb03-5137-809c-f2081571059f to the new Baton invite EE40C63838424246B9D0E5F0A55C78A6. The original one-shot observer falsely timed out because ChatGPT rendered an inline code span without its literal backticks. A separate read-only verification after independent reload recovered the same reply ID and content SHA-256 (5e5d2f90979d9c671495d2ce35fd6bcea043ff9193770ff52073aeb8655209bd); the old timeout receipt was retained, no resend occurred. Reconciliation record: ~/.local/state/baton/continuity/2026-11-13-som-onboarding-reconciled.json.

Søm described a new generation race: bridge A performs a legitimate local test, bridge B replaces A in the same /c/ conversation, and A's delayed successful receipt must never mark B READY or clear B's pending flag. The reference bridge now uses per-session object identity plus new generation and nonce checks at the bootstrap, observer and result callbacks. Dedicated negative tests simulate stale A versus B with same chat ID and even duplicate nonce. This is local and reference-level verification, not a multi-profile production deployment.

Søm also challenged the single combined UNCERTAIN status: an outbound bridge may be working while one earlier external message remains uncertain. The native panel now displays bridge state and delivery uncertainty in **separate** labels. An unverified remote delivery does not invalidate a local bridge handshake or authorize a resend. Both findings have been added to new dynamic FAQ entries.

The observer now has a narrow fallback for rendered Markdown inline-code: only source-bound, uniquely Baton-marked user messages can compare after removing inline backticks. Ordinary messages still require exact match. Unique adjacent assistant turn and source conversation markers remain mandatory. This was checked against the real original Søm reply, and its negative controls are in test_baton_chat_observe.py.

Latest Greg regression: 145 tests passed with Qt offscreen and ResourceWarning treated as errors. The pinned running and preview Baton releases were not modified, and the historical PAUSE_UI_WRITES digest remained unchanged. This work remains an isolated candidate PR until re-staged and explicitly run with real authenticated sessions.
