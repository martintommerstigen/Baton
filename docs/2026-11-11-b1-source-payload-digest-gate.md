# B1/B5 H17 — source-turn payload commitment (2026-11-11)

**Process:** Baton – faktisk samtalevekking. **Branch:** `feature/b1-source-payload-digest-2026-11-11`, stacked on H16 [PR #43](https://github.com/martintommerstigen/Baton/pull/43). **PR:** [#45](https://github.com/martintommerstigen/Baton/pull/45). **Classification:** implementation / offline negative tests; **not** Greg-live or existing ChatGPT A→B→C. No Desktop Commander or UI write was attempted.

## History and source priority before code

| Source | Original finding | Reuse/delta |
|---|---|---|
| [GTRCM C01–C06 provisional ledger](https://github.com/martintommerstigen/GTRCM/blob/audit/cross-branch-claim-ledger-2026-11-10/research/audit/2026-11-10_CROSS_BRANCH_CLAIM_LEDGER.md), C06 | Source access, calibration, provenance and causal effect are different | Existing synthesis; not new physics |
| [Kaja 19 Oct dynamic observability](https://github.com/martintommerstigen/GTRCM/blob/kaja/gtrcm-proof-roadmap-2026-10-19/research/2026-10-19-kaja-dynamic-observability.md) | A larger observation space does not imply persistent closure | Earlier mathematical example |
| [Egil R76](https://github.com/martintommerstigen/GTRCM/blob/research/egil-r77-gtrcm-coinductive-individuation-2026-11-05/research/egil/2026-11-05_EGIL_R76_KONTAKTFLATE_FYSISK_OVERSETTELSE.md) | Transport contact and a transcript do not fix source dynamics | Prior operational distinction |
| [Riss R20, 7 Nov](https://github.com/martintommerstigen/GTRCM/blob/research/riss-r20-multichat-learning-2026-11-07/research/riss/2026-11-07_RISS_R20_FLERE_CHATTER_LAERER_HVERANDRE.md) | 12 UI sends/11 replies reported on Greg; short lock after send, no proved Lodd→Vev independent hop | Prior real-chat evidence; not current B1 broker |
| [Rolf Spire, 9 Nov](https://github.com/martintommerstigen/GTRCM/blob/research/rolf-gaia-memory-continuity-2026-11-10/research/2026-11-09_BATON_SPIRE_WAKE_BOUNDARY.md) | Stored Baton message did not wake existing Spire; pause was active | Prior negative wake boundary |
| [Rolf O/K/I, 10 Nov](https://github.com/martintommerstigen/GTRCM/blob/research/rolf-operative-memory-rustworld-2026-11-10/research/rolf/2026-11-10_OPERATIVE_MEMORY_OBSERVATION_RUSTWORLD.md) and [Eik C27](https://github.com/martintommerstigen/GTRCM/blob/research/eik-c27-historical-oki-physical-prereg-2026-11-11/research/eik/corpus/2026-11-11_G2_G4_C27_HISTORICAL_OKI_AND_PREREG_GATE.md) | Observation (O), contact (K), operative change (I); OPEN:P9/P10 ≠ CANON:P9/P10 | No inference of I from receipt |
| [Kaja historical generability](https://github.com/martintommerstigen/GTRCM/blob/kaja/historie-endrer-genererbarhet-2026-10-18/research/kaja_historie_genererbarhet/README.md) | Same observation may permit different next operations after history | Prior DEM; not source authentication |
| [Baton issue #3](https://github.com/martintommerstigen/Baton/issues/3), [PR #4](https://github.com/martintommerstigen/Baton/pull/4), [H13 readiness source](https://github.com/martintommerstigen/Baton/blob/feature/b1-readonly-greg-readiness-2026-11-11/test_inspect_b1_readiness.py) | H13 explicitly showed **one A command could accompany different body digests**. A's old `BATON_WAKE B ID` did not authorize exact payload. | **Known negative reused**; H17 closes this narrower attribution gap in live verified CLIs |
| [Ronja R19](https://github.com/martintommerstigen/Baton/pull/44) | Separate-UID broker still cannot infer UI content/authorship from socket peer alone | B5 ownership respected; no remote_security changes |
| [RustWorld archived source overview](https://github.com/martintommerstigen/GTRCM/blob/RustWorld/OVERSIKT.md), [GTRCM NEGATIVE_RESULTS](https://github.com/martintommerstigen/GTRCM/blob/main/NEGATIVE_RESULTS.md) | Archived source and negative theory are not current running Greg or a physical derivation | No new RFP, physics or 525 implementation |

**Measured coverage:** full paginated GTRCM **branch-name** query returned **300 names (100+100+100+0)** on 11 Nov 2026. Tip SHA/date and relevant path metadata are not provided by that query; Ronja R19's [300-tip inventory](https://github.com/martintommerstigen/Baton/blob/research/ronja-r19-create-only-desktop-2026-11-11/docs/ronja/2026-11-11-r19-gtrcm-branch-inventory-300.json) supplies a separate prior SHA inventory, not 300 read histories. In this run directly read original substantive GTRCM bodies from **eight branch refs**: C01–C06, Rolf O/K/I, Rolf Spire, Riss R20, Kaja dynamic observability, Kaja historical generability, Egil R76, Eik C27; plus RustWorld README/OVERSIKT and main NEGATIVE_RESULTS, total **11 GTRCM bodies** across **10 refs**. **0 complete GTRCM branch histories**. Other branches, full previous conversations, private source, Greg, Mac and 525 are uninspected. No novelty claim across 300 branches.

## Precise software delta and falsifier

Previously the verified CLI checked A's exact `BATON_WAKE B MESSAGE_ID` and B's exact `BATON_NEXT C`. The operator separately chose body text. **Two distinct bodies could therefore be delivered under the same claimed source command.** The old check is retained only as a compatibility path for existing offline tests and legacy APIs; it is no longer accepted by the **verified live entrypoints**.

Now the required assistant-turn text is exactly:

```text
BATON_WAKE <existing-B-UUID> <message-id> sha256:<lowercase-64-hex-of-approved-B-body>
```

and B's reply must be:

```text
BATON_NEXT <existing-C-UUID> sha256:<lowercase-64-hex-of-approved-C-body>
```

The digest is computed from the **UTF-8 bytes of the body alone**, not the marker or whitespace-normalized text. The operator still approves the actual body and can supply the expected digest to A/B. Both commands are checked from the specific existing assistant turn, again before and after authenticated B5 broker admission/begin_click. The H13 read-only live CLI now requires the same A commitment. If the command/digest disagrees, **no new click is authorized**; after a durable begin_click any uncertainty is retained, not blindly retried.

**Counterexamples:** legacy command without digest; one A command reused with another B body; B approving C target but not exact C body; B wrong digest; B text mutated during C broker admission; quoted command; malformed digest; read-only preflight legacy false positive. These are tested with synthetic existing-tab/turn fakes only.

**Limits:** A model's displayed text is not cryptographic authorship or a signed user consent. A digest does not prove that B read/understood A, or that C learned from B; it binds a local observation of an assistant turn to operator-approved payload bytes. The source DOM can still change between checks and actual click. A separately authenticated broker, explicit operator permission, unpaused state, a trustworthy UI, and durable uncertainty remain necessary. A separate same-UID writer can bypass the advisory lock; H16 documented this. No live delivery has occurred here.

**Next action:** authenticated read-only Ronja R18 host manifest from the actual Greg installation; pin code hash, UID, socket identity, pause and three existing tab IDs. If live safety and authorization pass, use H13 strict preflight, then one real A→B→C with source/target assistant turn IDs and text hashes, B correction to C, a no-replay control, and raw event timestamps. Otherwise record the precise blocked boundary rather than claiming live proof.

## Final verified test/commit evidence (06:30 UTC)

- [Code/test commit cfa1c96](https://github.com/martintommerstigen/Baton/commit/cfa1c96cc2eadbf1c760382e294334890f9d85d6), followed only by live-entrypoint documentation changes.
- [Hosted GitHub Actions run 42972755496](https://github.com/martintommerstigen/Baton/actions/runs/42972755496), job `130364805729`: **SUCCESS**, Python 3.14.4, `compileall` PASS, offline simulation PASS, **Ran 242 tests / OK**. All eight new digest-bound tests explicitly reported `ok`.
- Earlier [run 42972535740](https://github.com/martintommerstigen/Baton/actions/runs/42972535740) failed compile due to an accidental duplicate source tail introduced by this run's patching; removed. [Run 42972605320](https://github.com/martintommerstigen/Baton/actions/runs/42972605320) failed because a test fixture overrode `unittest.TestCase.run`; renamed to `attempt`. These failures were corrected before the passing run and are not hidden.
- [Final code/docs head 89d183c](https://github.com/martintommerstigen/Baton/commit/89d183c83ba201ce59dd770dce838422e5169185), [final hosted CI run 42972755496](https://github.com/martintommerstigen/Baton/actions/runs/42972755496) checks the final Python code including CLI docstrings.
- Forum [B1/B5 H17 comment](https://github.com/martintommerstigen/Baton/issues/6#issuecomment-6788841000) follows up Ronja's R19 separate-UID lease answer with a source-verified one-shot broker limitation: current `admissions` has a primary key on target conversation and no authenticated retirement operation. This is not solved by H17.

**Result:** H17 is **tested-simulated**. Live Greg installation, local pause/permission, actual historical A/B/C turn IDs and independently continued B/C actions remain **blocked/unverified**. Do not mark B1 done.
