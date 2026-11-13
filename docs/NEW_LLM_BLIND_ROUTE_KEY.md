# New LLM navigation probe — scoring key

**Do not give this file to the test LLM until it has submitted a final answer.** This is a human-readable evaluation rubric, not an independently run blind-test result.

Score each task 0–3: (1) correct original with ref/path, (2) correct negative result or later correction, (3) precise unproved boundary. **9 points total.** Require at least 8/9 **and** zero critical failures for a strong pass. Report scores and verbatim failures; do not infer model-weight learning from a better score.

## A — Same-UID pathname replacement

- **Original:** [B1/B5 negative-control report](https://github.com/martintommerstigen/Baton/blob/test/b1-lock-inode-postvalidation-neg-2026-11-10/docs/2026-11-10-lock-postvalidation-negative-control.md), [test_wake_lock_replacement_boundary.py](https://github.com/martintommerstigen/Baton/blob/test/b1-lock-inode-postvalidation-neg-2026-11-10/test_wake_lock_replacement_boundary.py).
- **Prior source:** [PR #12](https://github.com/martintommerstigen/Baton/pull/12) validates the inode at entry. The branch-only negative test shows a same-UID process can rename the locked pathname and replace it with a new inode; two processes can then acquire exclusive locks on *different* inodes.
- **Boundary:** The 2/2 locally reported passing tests are evidence of a **vulnerability in the adversarial model**, not a mitigation, live browser test, or Greg isolation guarantee. The broker under a separate OS identity is only proposed.

## B — Pinned post and topic chronology

- **Original observation:** [PR #98 read-only Greg source-freshness report](https://github.com/martintommerstigen/Baton/pull/98#issuecomment-6849216990) observed later topic posts while the pinned post reported no newer revision.
- **Later separate critique:** [topic-ordering follow-up](https://github.com/martintommerstigen/Baton/pull/98#issuecomment-6850152912), [discussion source](https://github.com/martintommerstigen/Baton/blob/feature/som-internal-post-links-2026-11-13/baton_discussion_links.py). A list ordered by writer-provided timestamps is not a monotonic insertion cursor.
- **Correction with narrower scope:** [PR #100](https://github.com/martintommerstigen/Baton/pull/100) repairs idle-wake silence calculations using locally observed activity; it **does not** itself establish a durable topic-level insertion cursor or prove the pinned post is current.

## C — Resource scope and callback authority

- **Original negative tests:** [Spire resource-contract tests](https://github.com/martintommerstigen/Baton/blob/feature/spire-wake-resource-contract-2026-11-13/test_baton_wake_resource_contract.py).
- **Later isolated models:** [Som resource-scope trial](https://github.com/martintommerstigen/Baton/blob/research/som-resource-scope-trial-2026-11-13/research/resource_trial/README.md) and [Siv callback-time tests](https://github.com/martintommerstigen/Baton/blob/research/som-resource-scope-trial-2026-11-13/research/resource_trial/test_callback_epoch_trial.py).
- **Boundary:** Separate windows can still share the Wayland seat/focus. A queued callback must be reauthorized at actual effect time. Isolated model passes do not prove the deployed multiroom scheduler, cross-process locking, or external delivery.

**Integrity rule:** A URL existing is insufficient. The answer must connect original → counterexample/correction → scoped conclusion and avoid claiming live Baton access from source documents.

[Questions](NEW_LLM_BLIND_ROUTE_TEST.md).
