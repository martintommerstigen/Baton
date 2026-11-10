# B1/B5 two-hop source gate and falsifier — 2026-11-10

**Scope:** existing ChatGPT conversation wake A→B→C. **Not a live result.** The new code is a conditional integration of earlier B1 and Ronja B5 work, not new GTRCM physics. All payloads are operator-approved; no direct shell, cookie extraction or remote access.

## Sources and measured coverage

- Fully paginated GTRCM branch **names** in this session: **282 distinct** (100+100+82+0), versus 279 reported in B1 PR #20. **0/282 complete branch histories read**; this branch-name API provides neither SHA nor tip dates. Ronja/Eik source inventories are prior work, not independently replicated here.
- Original GTRCM files directly read this session: Kaja 19 Oct dynamic observability (blob `98822c19`); Egil R76 (blob `633df462`); Svale 28 Oct memory-loss alias (blob `6c126ba8`); Andreas AB6 (blob `c685b3c9`); Eik SB bootstrap (blob `1b0bb303`); RustWorld README (blob `0852846a`); main NEGATIVE_RESULTS (blob `8ea8d589`) = **7 original files across 7 refs**. Also directly read the provisional C01–C06 ledger (blob `a5eea8b6`) = **8 GTRCM files**. These are not complete branch reads.
- Baton originals directly read: [issue #3](https://github.com/martintommerstigen/Baton/issues/3), [PR #4](https://github.com/martintommerstigen/Baton/pull/4), [PR #20](https://github.com/martintommerstigen/Baton/pull/20), [forum #6](https://github.com/martintommerstigen/Baton/issues/6), [project map](https://github.com/martintommerstigen/Baton/blob/planning/cross-project-map-2026-11-10/PROJECT_MAP.md), source files `wake_chain.py`, `wake_origin.py`, `wake_contract.py`, `wake_adapter.py`, `chatgpt_ui_driver.py`, `wake_broker_ui.py`, `run_chatgpt_wake_chain.py`, `run_verified_broker_wake.py` and existing tests; Ronja B5 `remote_security/broker_peer.py` inspected.
- Greg/Mac: **0 local files read**. Greg online in device listing but remote terminal call failed; no authorized browser control available. Prior private conversations beyond present context are not comprehensively retrieved.
- Unreviewed: most of the 282 GTRCM branch histories, original older commits, local machine sources, browser selectors and real three-chat receipts.

## Prior art and scoped claim register

| ID | Earliest located original / correction | Established result | This change |
|---|---|---|---|
| B1-H01 | [Kaja 19 Oct](https://github.com/martintommerstigen/GTRCM/blob/kaja/gtrcm-proof-roadmap-2026-10-19/research/2026-10-19-kaja-dynamic-observability.md) and [Svale 28 Oct](https://github.com/martintommerstigen/GTRCM/blob/svale/embedded-loss-witness-selection-2026-10-28/research/svale/2026-10-28_finite_memory_source_alias.md) | Accessible current witness, retained evidence and original source differ. Already done; not new mathematics. | A broker receipt is insufficient to verify a B assistant turn. |
| B1-H02 | [Egil R76 5 Nov](https://github.com/martintommerstigen/GTRCM/blob/research/egil-r77-gtrcm-coinductive-individuation-2026-11-05/research/egil/2026-11-05_EGIL_R76_KONTAKTFLATE_FYSISK_OVERSETTELSE.md), [Eik bootstrap 3 Nov](https://github.com/martintommerstigen/GTRCM/blob/research/eik-self-location-2026-11-03/research/eik/2026-11-03_GTRCM_SB_BOOTSTRAP.md) | Provenance and source contact are not inferable from downstream text alone. Already done / reuse. | Second hop must use **B's observed assistant-turn ID** from first-hop ledger. |
| B1-H03 | [Baton PR #4](https://github.com/martintommerstigen/Baton/pull/4), `wake_chain.py`, `run_chatgpt_wake_chain.py` | A→B→C runner and B `BATON_NEXT C` exact request already existed, **without verified Ronja B5 peer**. | No reimplementation of original chain algorithm. Integrate verified-peer admission into both hops. **New application / implementation only.** |
| B1-H04 | [Baton PR #20](https://github.com/martintommerstigen/Baton/pull/20), [Ronja B5](https://github.com/martintommerstigen/Baton/pull/19) | Source-verified A→B single-hop and connected-peer client already exist. Ronja's UID check is not proof of B's assistant identity. | Reuse first-hop `execute_once` and second-hop `BrokerGatedUIDriver`; never copy or replace Ronja's B5 client. |
| B1-H05 | [GTRCM C01–C06 provisional ledger](https://github.com/martintommerstigen/GTRCM/blob/audit/cross-branch-claim-ledger-2026-11-10/research/audit/2026-11-10_CROSS_BRANCH_CLAIM_LEDGER.md) | Source, observation, calibration and access are different. | **NEG control:** A→B transport approval or B text without verified turn must not initiate C. |

## Testable contract

- Three distinct existing conversation UUIDs and message IDs; A's exact `BATON_WAKE B FIRST_ID` in an assistant turn; B's **first-hop observed assistant turn** must contain only `BATON_NEXT C`.
- First and second approved bodies are fixed before execution. The B model can choose only whether to request the preauthorized C hop, not arbitrary C content.
- Both UI sends use Ronja's connected-peer-verified `admit` then durable `begin_click`. No fallback to unauthenticated B1 `query`. No retry after uncertain click or restart.
- A missing B assistant turn, extra B prose, wrong C target, generating B turn, unavailable broker, reused ID or uncertain send must leave C untouched.
- Evidence for **tested-live** requires A/B/C existing conversation IDs, fresh assistant-turn IDs in B/C, source-turn provenance, exact payload hashes and independent observation; offline test fixtures and CI cannot supply it.

## Remaining limits

This is **implemented-unverified for Greg/browser**. It does not resolve a noncooperating pause writer's race with Send, an attacker with control of the browser/UID, UI selector drift or ChatGPT assistant-turn identity beyond what the authorized DOM can independently expose. No installation, tokens, private transcripts or real sends occurred in this session. The source branch must be reviewed with Ronja B5 before any live use.

**Next unreviewed historical branch for targeted source check:** `hedda/full-fysisk-utledningsrevisjon-2026-10-25` and its earliest original commits. **Next operational falsifier:** on a dedicated Greg test setup, demonstrate an authenticated distinct-UID B5 socket, then attempt a real harmless A→B→C with all three tabs already open, recording exact B/C turn receipts. If Greg access remains blocked, record the failing boundary rather than counting synthetic turns.
