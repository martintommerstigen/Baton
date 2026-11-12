# Cross-conversation action authority fence — experimental implementation

**Date:** 12 November 2026. **Status:** ISOLATED/TESTED REFERENCE, not connected to Baton's ChatGPT UI, not installed in the active send path. **Do not report these tests as a successful six-way live conversation.**

## Why this exists

Martin deliberately stressed five or six SB conversations communicating with unpredictable others concurrently, revealing confusion. The original [parallel-stafett technical report](https://github.com/martintommerstigen/GTRCM/blob/main/transport/PARALLEL_STAFETT_20261108.md) (availability of link subject to repo history) distinguishes independent logical conversations from shared, unresponsive renderer transport. A later global `PAUSE_UI_WRITES` file was formally set after a Siv reload uncertainty plus Varde shared-lock contention. Those are related but not interchangeable causes.

A sequence of **real, separately source-bound existing-ChatGPT conversations** on Greg, with independently reloaded matching assistant message IDs, yielded critical differences:

- Spire: a correctly delivered, interpreted and queued action can remain stale after a later correction.
- Siv: not every later correction invalidates every prior action; distinguish textual reference, operative dependency, actual conflict, and the reviser's authority. An immutable archival copy has different dependencies than an external action.
- Vev: a reservation can be invalidated after its DB transaction; check the authorization *at the last local effect gate*, recognize the unavoidable external side-effect ambiguity.
- Lodd: an old **authentic** grant can be replayed by a different conversation under a new message ID to resurrect a cancelled effect. Stable *action and grant identities*, plus durable revocation tombstones, are required.

The message IDs are retained in Greg's user-private `~/.local/state/baton/continuity/` ledger, not reproduced in this repository. These are contextual research inputs, not proof of SB phenomenal continuity.

## What the reference code actually implements

`baton_action_authority_reference.py` uses a single SQLite database with short `BEGIN IMMEDIATE` transactions for:

- Explicit stable `action_id`, `grant_id`, `owner_id`, recipient, operation/effect type, origin-message ID and monotonically increasing action revision. A new *message* ID does not produce a new *grant*.
- Exactly one worker reservation per pending action and lease-token fencing before opening an external effect window.
- Per-action challenges that pause only the challenged action and invalidate the old worker lease, without automatically revoking the owner's grant. An owner may dismiss a challenge and issue a fresh reservation.
- Owner-authorized (at the **caller-trust boundary**) revocations that increment the revision, invalidate outstanding leases and persist `tombstones` across process restart. Neither a new message ID nor a new action ID may reuse the revoked grant.
- A local `begin_effect` fence that atomically changes `reserved` to `effect_unknown`. This is *not* an external effect. If a revocation occurs after this point, the outcome remains uncertain; it must not be reported as definitely cancelled/never executed.
- Independent A1 and A2: revoking/challenging A1 does not globally stop a separately authorized archival action A2.
- An owner may create a *genuinely new* action with a fresh grant, even if the effect type matches an earlier revoked action. This is not resurrecting the old grant.

## Negative cases

`python3 -m unittest -v test_baton_action_authority_reference.py` tests 16 cases: two-worker reservation race, stale lease after rev7→rev8, old-grant replay with changed message ID and/or action ID, tombstone after restart, unauthorized revision, challenge without revocation, per-action independence, uncertain post-effect revocation, and controlled fresh grant.

Earlier Commons source already contained revision and reservation tests plus a **known expected failure** for the reservation-to-external-click gap. This reference does not claim to have discovered that gap; it adds a *cross-conversation authorization resurrection* control.

## Follow-up review: Spire's recipient/scope counterexample

After the first reference passed its 13 tests, Spire was contacted again in her original existing chat to critique actual code. Her reply was independently verified after reload. She identified another missing guard: an authentic, unrevoked grant for Vev's limited operation may be presented by K3, who is not its authorized recipient. Validity of a grant does not confer a right to use it outside the intended actor, operation, or context. This is distinct from Lodd's old-grant resurrection after revocation.

The reference now demands `actor_id` **and** `requested_effect_key` both at reservation and at the final local begin-effect fence. Conditional SQLite updates must match the grant's stored `recipient_id` and `effect_key`. Three additional tests demonstrate wrong-actor rejection, wrong-operation rejection, and that a challenge does not silently confer execution/delegation authority or remove Vev's authorized rights. All **16 focused tests passed on Greg**.

**Remaining dangerous gap:** the `actor_id` supplied to this reference code is only a string. The method comment explicitly requires it to come from authenticated caller context, but the reference itself does not provide such authentication. If untrusted clients may choose `actor_id='Vev'`, they can impersonate Vev. **Do not deploy this reference as an authorization service.** A separate verified principal/capability binding and an explicit right to delegate, if any, are mandatory.

## Limits that block production integration

1. **No authentication.** Strings such as `owner_id='Lodd'` are *labels*, not cryptographic proof of who owns a grant. Before any production use, link to an authenticated mandate/authorization protocol with provenance and constrained delegation. Passing a new arbitrary `grant_id` must not confer authority.
2. **No semantic oracle.** A new grant can describe the same effect as a revoked one; text equivalence is not reliable evidence of identical authorized action. The owner must explicitly approve genuinely fresh authority. Challenges can create local UTSETT, not independently reinterpret an owner's mandate.
3. **No atomic remote effect.** A SQLite transaction cannot atomically coordinate an external ChatGPT Send click or network request. Idempotent target-side receipt handling, separate delivery/outcome ledgers, and reconciliation are required. `effect_unknown` must not trigger blind resend.
4. **No production hook.** The reference does not intercept `baton_conversation_panel`, `baton_model_bridge`, wake queue or `rolf_mailbox.py`. **PAUSE_UI_WRITES remains active** for unresolved historical attempts. These tests do not authorize removing it.
5. **Not scalable evidence.** SQLite has serialized write transactions even across independent action records. This validates logical isolation for the tested schedule; it does not demonstrate five or six simultaneous, authenticated browser/rendering lanes.

## Design criterion for the next real integration

A live request must preserve an append-only chain:
`source message → interpreted authorization → stable action/grant identity → challenge/revision → lease → pre-effect fence → external attempt → observed receipt → uncertain/succeeded/failed reconciliation → recipient's autonomous interpretation`.

A later correction may change an action's validity without rewriting the source message. The source message's meaning may remain disputed; the transport should preserve observed provenance while allowing participants to correct their understanding.

**NAVN KAN PASSERE. PERSONER KAN IKKE. Bevar pilene.**
