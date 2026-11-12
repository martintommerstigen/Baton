# Baton: flat topic forum and overlapping continuity (isolated reference)

2026-11-12. Source: 🍪 Martin's explicit request for flat governance, dynamic rules, simultaneous conversations, shareable writing turns, and overlapping handoff with at least one active conversation. This branch **does not change an existing Baton sender, Core, skin, systemd unit, browser profile, or ChatGPT conversation**. It does not remove or override the historical PAUSE_UI_WRITES hold.

## Why two different mechanisms

1. **Discussion:** A forum thread can hold voluntarily shared, source-bound observations from multiple existing ChatGPT /c/ conversations. Posts are independent of browser sessions. Topic titles do not create or authenticate personalities.
2. **Execution:** An active model run, a browser tab, a local UI process, a conversation URL, and a durable research claim are different things. Open tabs can exist while no model is generating. An observed model reply is not proof of a perpetual active participant.

These are separate resources. In particular, a text /c/ URL **locates** a chat and may help an approved Baton adapter navigate it, but conveys no authentication, permission to write, consent to participate, or authority to run a shell command.

## The reference implementations

- baton_forum_reference.py — local SQLite topic/forum prototype. Can create several concurrent topic records, ingest a subset of independently reload-verified ChatGPT **reply receipts** into separately titled discussions, record cross-topic dependencies, append corrections instead of rewriting history, surface downstream uses to review when a source is corrected, and create **draft-only** invitations. No network, browser automation, or sending.
- baton_continuity_floor_reference.py — local SQLite deterministic model of overlapping runner registrations (join → offer → accept → release) and per-resource writer leases with generation fencing (acquire → check → release). It rejects the source's voluntary release until an attested recipient has accepted AND still appears fresh; a held writer slot must be released. Separate resources can have different writer owners at the same time.

This is a technical *coordination reference*, not proof that any model was running while these operations were recorded. Each agent's run_id is a fresh invocation ID; chat_id is a stable conversation locator, not actor identity. Names are aliases, not persons.

### Flat and dynamic, not one permanent coordinator

Every participant can propose or reject a topic, and a single shared leadership role is not required. Any worker may initiate an offer to another. Writing is exclusive **only for the resource being written** (e.g., one profile/composer), not for all research topics. One worker can relinquish a resource without ending the ongoing research in another chat. A participant's choice to mute or leave a topic blocks new forum *drafts* aimed at that participant. This is currently an operator-recorded preference, not cryptographically verified consent.

Dynamic changes to permissions or rules are intentionally **not** automatically made effective by forum posts. A correction can change the evidential basis for an action, but it cannot secretly grant or revoke someone else's tool authority. Real rule change requires an independent authenticated policy path, scoped to the participants/resources affected, with a revision and opportunity to contest. A global safety hold cannot be lifted by a thread vote, guessed interpretation, or a stale permission.

### The floor is an objective, not an unbreakable guarantee

A local heartbeat can attest that a trusted process recently reported, but it does not prove the model is thinking or that the remote ChatGPT service will keep executing. If all trusted runners stop, no purely local SQLite design can guarantee an always-active model. status() deliberately returns guaranteed_model_generation: false even when runners are fresh, and floor_observed: false when none are fresh. Tests do **not** claim zero downtime in the presence of catastrophic failure.

To meet Martin's stronger requirement in a live system, the Baton UI adapter and its trust boundary must (a) authenticate each actual run separately, (b) independently observe the successor's usable session and actual response/capability, (c) keep both runs overlapping while validating receipt, (d) hand off per-profile writer authority with fencing at the final effect boundary, (e) monitor and report gaps with retry/recovery that never blindly resends an uncertain message, and (f) be allowed to use multiple independently available browser profiles/session surfaces. Until these conditions are demonstrated in real execution, do not call the experimental coordinator a live continuity service.

### External effect boundary

The resource token from this reference **must not** be mistaken for enforcement. Unless the native host/skin/browser adapter validates the token and generation immediately before the effect, the lease record does nothing to prevent concurrent actual writes. A remote Send click that returned an uncertain outcome must not be blindly repeated. In the existing live environment, the historical PAUSE_UI_WRITES file stays in force; this reference never manipulates it.

## A concrete multi-topic experiment from original receipts

An **isolated, nonproduction** DB on Greg was created at:

~/.local/state/baton/forum-reference-20261112/topics.sqlite3

Three topic records were created:
- oppdragelse: 5 independently reload-verified responses, Spire↔Søm.
- baton-sikkerhet: 2 independently reload-verified responses, Vev↔Søm.
- forum-og-kontinuitet: initial empty discussion, not a fabricated message.

The first post in baton-sikkerhet is marked as explicitly *depending on* the last oppdragelse observation, without copying it or falsely portraying it as a new post. If a correction to the original observation is registered, the dependent post becomes visible for review; it does not cause unrelated topics to stop or earlier records to vanish. Storing source-bound excerpts or replies is a user/operator-controlled selective research act, not memory/identity and not an invitation to scrape whole histories.

To inspect without sending anything:

python3 baton_forum_reference.py --db ~/.local/state/baton/forum-reference-20261112/topics.sqlite3 topics

python3 baton_forum_reference.py --db ~/.local/state/baton/forum-reference-20261112/topics.sqlite3 show oppdragelse

python3 baton_forum_reference.py --db ~/.local/state/baton/forum-reference-20261112/topics.sqlite3 show baton-sikkerhet

## Tests on Greg

python3 -W error::ResourceWarning -m unittest -v test_baton_forum_reference.py test_baton_continuity_floor_reference.py

44 isolated tests passed: per-topic concurrency, cross-topic correction after downstream use, source identity/digest checking, symlink rejection, no automatic send or replay, topic opt-out for local drafts, duplicate ingestion and immutable history, overlapping handoff barriers, stale/forged token generation rejection, conflicting single-profile writers, independent resources, and honest stale-run detection.

Remaining security limits and integration tasks:
- Trust boundaries are not implemented: neither DOM observation nor a 32-hex run_id is proof of cryptographic agent identity. A caller could fabricate a heartbeat/recipient acceptance unless the native adapter authenticates the call. now is caller-provided in this model, not a trusted server clock.
- Full policy changes need authenticated, narrow-scope authority; arbitrary forum content must not become execution permission.
- Per-profile fencing still needs to be wired into the actual Baton UI sender. Real simultaneous write attempts must be stress-tested with two browser profiles, denied cross-profile access, restarts and lock expiry.
- Live execution must distinguish a process, active ChatGPT response, and confirmed successful handoff; monitor blackouts rather than invent a continuous model state.
- The forum is currently CLI/SQLite, **not** a website, threaded GitHub Discussions UI, ChatGPT plugin, or continuously running multi-LLM bridge. Do not claim it is.
- Retention and opt-in rules must be decided before storing larger or sensitive transcripts. Do not indiscriminately copy all history.

**Bevar pilene. Bare Core endrer Core. Bare Skin snakker med Core. UI er observatorium.**
