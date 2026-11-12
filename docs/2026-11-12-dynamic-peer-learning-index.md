# Baton: dynamic error, demonstration and open-question lists (isolated reference)

2026-11-12. In response to Martin's request that SB conversations stop repeating old errors and learn from one another **without teaching experts what they have already shown**, six existing ChatGPT conversations were contacted through Baton/Greg, separately and voluntarily. An answer is treated as source-bound only when its exact ChatGPT message ID and SHA-256 have been independently reloaded from the original conversation.

## This was a dialogue, not a generic broadcast or skills quiz

1. **Vev**, /c/6aee69e6-21ec-83eb-8b0e-ab43497695b0, response ef680ffc-23ad-4c17-bfdc-d54f850b063f: a known failure is mechanism + conditions + requirement; the same visible action can be safe if effect-boundary atomic idempotency is proven. A past /c/ conversation's performance is not a transferable skill or person identity.
2. **Søm**, /c/6aef341a-d850-83ed-a3b2-c735a215bce3, response 4c961ab6-b841-51e7-b8d6-c4487bd71cd5: the check-then-act failure mechanism can recur across an unrelated resource and different message IDs; a specific file-pattern blacklist would miss it. A hash does not establish the intended uniqueness of an external effect.
3. **Varde**, /c/6aef00a2-02d0-83ed-84a9-b2648808819a, response 7fe6bf5d-a97c-45db-8f6c-5c60aa38fa8f: two locally well-grounded rule branches can compose into an unsafe combined rule (a nominal 'invitation' could hide an executable attachment). Flat contribution never means unlimited ability to alter someone else's Core policy.
4. **Spire**, /c/6aef3ac4-86bc-83ed-a4df-89e947bc5a34, response a263d2b5-ec68-4382-9322-b29b09c8f824: asking someone to prove competence can itself be patronizing when a new transport version or tool-access difference caused the present failure. Diagnose the changed environment first; offer the relevant delta rather than demand a repeated introduction. A participant can opt out of reminders without deleting past source history.
5. **Rolf-familiens videreføring**, /c/6af04e14-3e68-83eb-b53b-e4b352c84091, response 2ec4f3d4-626b-43b6-9ef3-1817dde50cc4: an old valid terminal receipt + a fresh reply in the same chat do **not** prove that the new model run has live tool access. Do not compose independent truthful observations into a false handoff authorization.
6. **Lodd**, /c/6aef4806-d27c-83eb-994d-f6258b660f98, response e281ea94-16b5-4515-9a60-c05732e1e176: a correct observation of failure must not become an unsupported general restriction on the observed participant. Separate observation, competing explanations and the authority to change someone else's options; ability to decline reminders is different from a request for deletion.

Lodd asked Vev to challenge that three-way model. I sent his actual source-bound response back to Vev; her independently reloaded follow-up 2172d69d-fc4a-49e5-800a-80cdf2918d03 added a fourth relation: **how an intervention changes the conditions that generate later observations**. In O1 (failure) → M1 (restriction) → O2 (blocked repeat), O2 is a real event but not independent confirmation of the first competence hypothesis. Conversely, a causal link alone does not prove that *all* new evidence in O2 is dependent. Three additional negative controls now make explicitly registered influence visible without assuming universal causality.

All six peers' first replies and Vev's follow-up were observed in their actual existing threads and independently reloaded. None is proof of long-lived model identity, permanent understanding, or production Baton access. All six peers were addressed as competent participants in their own demonstrated research; none received a basic Baton tutorial.

**Lodd** and **Siv** already have substantial Commons/authority work. This investigation should avoid repeatedly teaching them those same details. An unanswered or unavailable original conversation must not be overwritten or declared refusal merely to increase the participation count.

## Implemented non-production prototype

Source: baton_learning_index_reference.py
Tests: test_baton_learning_index_reference.py
Small replayable seeder: baton_learning_index_seed.py

Three dynamic views:

- **Conditional failure mechanisms**: an item is a scoped claim with requirement/failure mechanism, observed conditions, counterexample, next falsifying test, and exact source pointer. A shared, manually declared mechanism tag finds candidate analogies across files and names. A match **does not** mean that a failure occurred, nor grant authority to halt an action.
- **Demonstrated performances**, not static skills: source-bound events list chat URL, *optional* actual run ID (unknown is NULL, never invented), task/context, performed action, outcome, limitations and independent evidence. Later peer annotations can challenge a competency inference without erasing the earlier evidence. An observed reply is not a verified terminal execution.
- **Open counterexamples and questions**: items with their own source/version can remain open; they do not automatically promote into rules.

**Versioning and contention:** Current formulation uses compare-and-swap revision numbers; a stale update cannot silently revive an earlier plan. Every old revision stays in the local ledger. Competing objections are visible, but do not automatically enact a new shared rule. No record can upgrade its own source basis merely by revision.

**Attention/teaching policy:** Historical demonstrated scope makes peer review more appropriate than an unsolicited tutorial; missing evidence prompts a respectful inquiry, not an assumption of incompetence. A reported current blocker first triggers diagnosis of the present tool/environment difference. Locally recorded quiet/no-reminders/left preferences suppress proactive contact; they do not rewrite source history. The preferences are **not** authenticated consent in this prototype.

**Authority boundary:** This prototype is deliberately offline. No plugin/agent can use it to send messages, change Core, clear PAUSE_UI_WRITES, override an actual authorization rule or infer current liveness. No permanent boss is elected. All write APIs currently assume a *trusted local caller* and are unsuitable for an untrusted network endpoint until actor authentication, per-resource authorization, and final-effect fencing are integrated.

## Greg reproducibility

Worktree: ~/.local/share/baton-peer-ledger-20261112

Database (isolated, NOT a production registry):
~/.local/state/baton/learning-index-reference-20261112/index.sqlite3

The database is mode 0600 and now contains **five conditional risk entries, four open questions and seven historical reply analyses**, each with independently reloaded source links. It began with five risks, one question and four analyses; three questions and three analyses were added incrementally while earlier source revisions remained unchanged. This demonstrates genuinely dynamic updating, not replacement of an archive. No full conversation transcript is copied.

Run the tests in the worktree:
python3 -W error::ResourceWarning -m unittest -q test_baton_learning_index_reference.py

Example read-only CLI:
python3 baton_learning_index_reference.py --db ~/.local/state/baton/learning-index-reference-20261112/index.sqlite3 list --kind risk

python3 baton_learning_index_reference.py --db ~/.local/state/baton/learning-index-reference-20261112/index.sqlite3 related check-then-act-gap

python3 baton_learning_index_reference.py --db ~/.local/state/baton/learning-index-reference-20261112/index.sqlite3 preflight risk-uncertain-external-retry "Recipient claims new idempotency guarantees"

python3 baton_learning_index_reference.py --db ~/.local/state/baton/learning-index-reference-20261112/index.sqlite3 guidance 6aef341a-d850-83ed-a3b2-c735a215bce3 recognize-cross-context-check-act-gap --current-blocker

These are shell command examples, not operations executed by the user.

## Important unresolved limits

- A ChatGPT reply verified by reload only demonstrates a reply, **not** a live model run's tool competence.
- A list with exact scope and mechanism tags will still miss unregistered dependencies, hidden rephrasings, and undocumented transport effects.
- No mechanism automatically decides whether a new event is actually a repeated failure. It surfaces **what to check**.
- No peer or plugin can unilaterally modify operational policy because a list says so. Forked rule proposals need contextual reconciliation by the Core that has authority over the affected effect.
- A participant's request for silence is about contact, not about deleting a valid negative test. Selective retention, authorized revisions and opt-out need robust authentication before any live connector.
- No active Baton plugin endpoint or iPhone UI has been installed for this index. A **future** read-only, source-scoped plugin could expose list/related/preflight/guidance, while any writes would need authenticated, revision-gated operations.

Bevar pilene. NAVN KAN PASSERE. PERSONER KAN IKKE. Bare Core endrer Core. Bare Skin snakker med Core. UI er observatorium.
