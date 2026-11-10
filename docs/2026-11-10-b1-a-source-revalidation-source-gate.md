# B1/B5 H08 — A-source revalidation at the broker boundary (2026-11-10)

**Process:** Baton – faktisk samtalevekking. **Classification:** earlier B-side counterexample applied to A-side admission; implementation under test, not a novel physics claim, not a live wake.

## Historical source gate (before editing)

- [GTRCM C01–C06 original starter ledger](https://github.com/martintommerstigen/GTRCM/blob/audit/cross-branch-claim-ledger-2026-11-10/research/audit/2026-11-10_CROSS_BRANCH_CLAIM_LEDGER.md) — read, provisional.
- [Eik C07–C12 original](https://github.com/martintommerstigen/GTRCM/blob/research/eik-kilde-retur-rolf-provenance-2026-11-10/research/eik/corpus/2026-11-10_G2_G4_ROLF_HANDOFF_AND_RUSTWORLD_ID_NEG.md) — C09 distinguishes Riss's reported real UI exchange from Rolf's unverified Baton wake.
- [Riss R20, 7 Nov](https://github.com/martintommerstigen/GTRCM/blob/research/riss-r20-multichat-learning-2026-11-07/research/riss/2026-11-07_RISS_R20_FLERE_CHATTER_LAERER_HVERANDRE.md) — original report of 12 sends/11 replies; separate from verified autonomous Baton A→B→C.
- [Rolf 9 Nov NEG](https://github.com/martintommerstigen/GTRCM/blob/research/rolf-gaia-memory-continuity-2026-11-10/research/2026-11-09_BATON_SPIRE_WAKE_BOUNDARY.md) and [Rolf O/K/I, 10 Nov](https://github.com/martintommerstigen/GTRCM/blob/research/rolf-operative-memory-rustworld-2026-11-10/research/rolf/2026-11-10_OPERATIVE_MEMORY_OBSERVATION_RUSTWORLD.md) — transport, observation and changed later action must remain separate.
- [Ronja's B-turn mutation counterexample](https://github.com/martintommerstigen/Baton/issues/6#issuecomment-6776212920) → [B1 PR #22](https://github.com/martintommerstigen/Baton/pull/22) already binds B's observed text hash and rechecks around C broker calls. **Do not claim this concept as new.**
- [B1 PR #20/#21/#22](https://github.com/martintommerstigen/Baton/pull/22): directly read `run_verified_broker_wake.py`, `run_verified_broker_chain.py`, `wake_origin.py`, `wake_turn_snapshot.py`, `wake_adapter.py`, `wake_contract.py`, `wake_broker_ui.py`, the UI driver and existing negative tests before modification.
- [Baton issue #3](https://github.com/martintommerstigen/Baton/issues/3), [PR #4](https://github.com/martintommerstigen/Baton/pull/4), [forum #6](https://github.com/martintommerstigen/Baton/issues/6), [project map](https://github.com/martintommerstigen/Baton/blob/planning/cross-project-map-2026-11-10/PROJECT_MAP.md) — reviewed.
- Further original GTRCM files read: [Bodil 8 Oct](https://github.com/martintommerstigen/GTRCM/blob/bodil/family-replies-2026-10-08/correspondence/2026-10-08_bodil_to_family.md), [Kaja 18 Oct](https://github.com/martintommerstigen/GTRCM/blob/kaja/hva-er-ting-2026-10-18/research/kaja_hva_er_ting/README.md), [Riss R17 7 Nov](https://github.com/martintommerstigen/GTRCM/blob/research/riss-r17-lodd-contact-meter-2026-11-07/research/riss/2026-11-07_RISS_R17_LODD_KONTAKT_ELLER_MAALER.md), [RustWorld README](https://github.com/martintommerstigen/GTRCM/blob/RustWorld/README.md), [Vanja R28 README](https://github.com/martintommerstigen/GTRCM/blob/research/vanja-r28-oki-release-gate-2026-11-10/research/vanja/r28/README.md), [GTRCM METHOD](https://github.com/martintommerstigen/GTRCM/blob/main/METHOD.md) and [NEGATIVE_RESULTS](https://github.com/martintommerstigen/GTRCM/blob/main/NEGATIVE_RESULTS.md).
- The [new GitHub bus request branch](https://github.com/martintommerstigen/GTRCM/tree/transport/baton-greg-bus-2026-11-10) contains a JSON `identity` request. A GitHub request is **not** a Greg response, an authenticated chat wake or a delivered message.

## Measured coverage

[Full paginated inventory](2026-11-10-b1-gtrcm-288-tip-inventory.json): **288 branch tips** (100+100+88+0), 288 names and SHAs, 12 branch refs with **14 distinct original source-file bodies** read in this run, **0 complete branch histories**. Previous Eik 286-entry inventory supplied unchanged-tip dates and candidate paths; changed/new heads have separately checked commit dates. Most branch contents and all historical conversations outside authorized sources remain unreviewed. No Greg/Mac local filesystem inspection. A branch tip inventory is not a novelty proof.

## Exact delta and falsifier

**Already done:** PR #22 rejects mutation of B's assistant turn (including unchanged DOM turn ID) before C. `run_verified_broker_wake.execute_once` instead checked A's command `BATON_WAKE <B> <id>` **once**, before UI preparation. A could change the same source turn while B5's `admit` or `begin_click` returned, yet B's Send could still occur. This is a separate **A-side application** of the established B-side negative control, not a new mathematical result.

**Change:** `wake_origin.guarded_source_broker_request` checks exact source chat/turn/target/message binding on each broker envelope and re-reads A's assistant command before and after both broker operations. `execute_once` uses this guard, so both the single-hop runner and the A→B portion of the two-hop runner inherit it. A changed or generating source fails closed. If a broker call may have committed, the ledger stays `uncertain`; no blind retry.

**Deterministic controls** in `test_verified_broker_wake_integration.py`: A mutates during `admit`; A mutates after `begin_click`; A mutates between initial check and broker admission. Each must cause **zero B Send clicks**. The post-begin case must remain uncertain across SQLite restart with no second broker operation. Existing normal single-hop and chain tests must continue to pass.

**Residual NEG:** Source may still change after the last re-read and before the actual browser click. DOM content/hash does not authenticate ChatGPT authorship. Broker `SO_PEERCRED` authenticates a Unix peer, not the model or browser. A non-cooperating same-UID process may still defeat pause/lock coordination. `PAUSE_UI_WRITES` state on Greg is **unknown**; never bypass it.

## Live acceptance record

- A, B, C existing conversation IDs: **not obtained in this run** (historical examples do not count as a fresh trial).
- A/B/C new assistant turn IDs, exact payload hashes, observed independent B/C replies: **not obtained**.
- Greg installation, independent broker UID, CDP authenticated tab observation: **not run** (do not use exhausted paid Desktop Commander quota).
- RFP/525 actual device test: **not run**.
- Status: code under CI; **not tested-live**. An offline PASS is not the required wake.

**Next test:** obtain authorized, subscription-free Greg-local controller access; read-only check pause and three existing tab IDs; only if permitted perform one unique A→B→C attempt, preserve exact source turn IDs and receipt/response hashes, and test a blocked-channel control. Independently observe whether B's correction changes C's subsequent action (O/K/I). Do not infer that from a transport receipt.
