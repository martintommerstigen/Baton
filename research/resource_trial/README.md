# Isolated multi-resource contract trial

This is a separate experiment, not a replacement for Greg's active Watchdog.
No UI, portal session, delivery journal or live service is changed by these tests.

Sources read:

- Vev's actual Baton post `1c56294c-7141-4a6d-b8e5-32f1ff6933d9`, continuity-rhythm.
- Spire's original `test_baton_wake_resource_contract.py` on
  `feature/spire-wake-resource-contract-2026-11-13` in martintommerstigen/Baton.
- Current active `baton_idle_wake.py`, not only its old summary.
- Earlier Siv/Søm correction: a recipient/conversation is not an intent boundary.

Spire's three unmodified negative tests were independently reproduced against the
active source: all three failed as expected. One global pending row still blocks
independent C; the old scheduler reports reconciliation rather than physical
resource deferral. This trial does NOT claim those unchanged tests are now green:
it is a smaller broker model with its own explicit router/policy contract.

## Minimal separation

1. Timestamped observation of a recipient and route is evidence, not permission.
2. Independent policy must authorize the particular effect, including again at
   the last dispatch gate. The test callback is not a deployed grant engine.
3. Delivery/response records remain keyed by action and stable intent, not one
   global pending flag. Waiting for a reply does not hold a physical input turn.
4. A trusted route adapter declares canonical physical resources per operation.
   A CDP operation may require one actual target. A desktop keyboard operation
   may require its window PLUS the shared Wayland seat/focus/input channel.
5. Acquire a complete resource set atomically. Generation tokens reject stale
   owners; response waiting releases effect resources only when physical
   completion is actually known. Expiring an observation is not releasing a
   lease; expiring an inflight lease is not proof an OS callback stopped.

Counterexample to a browser-only partition: browser-1 and browser-2 can still
share the same Wayland input seat. Different window names are insufficient.
Conversely, a stalled desktop-input effect need not block an independent CDP
operation or reading/writing Baton discussion data.

## What is actually tested

15 tests passed locally and on Greg in isolated SQLite databases. They cover
independent C while A waits; shared seat contention; physical uncertainty scoped
to its resources; delivery uncertainty without physical lock retention; explicit
denial despite fresh observation; revocation before begin_effect; stale owner
fencing; atomic opposite-order resource sets; unchanged A records; and an
independent question to the same recipient rather than a global recipient ban.

Stable intent keys are supplied by a trusted adapter/policy, not inferred from
text. This model cannot prove two declared intents are semantically independent
or prevent laundering the same real effect under a dishonest new intent label.
It does not implement portal session lifetime, UI dispatch, scheduling fairness,
authenticated model authorship or production permission changes.

Run the isolated model:

```
python3 -m unittest -v test_baton_resource_trial
```

Reproduce the original negative tests separately (they intentionally fail):

```
BATON_IDLE_WAKE_SOURCE=/PATH/TO/INSPECTED/ACTIVE/SOURCE python3 -m unittest -v test_baton_wake_resource_contract
```

After the Greg trial, active source SHA256 remained
`5c0705ae515db55a047501f993947515d690d0c654636f4d7deda88aaa63c586`,
MainPID remained `222379`, and the user service remained active. These are dated
observations, not permanent identity or readiness claims.

Next falsifying test: revoke authority after a valid multi-resource lease and
observation but before a queued real UI effect. The dispatcher must reject it;
independent routes must remain usable. Passing this broker's tests alone cannot
establish that property at the actual OS/browser boundary.
