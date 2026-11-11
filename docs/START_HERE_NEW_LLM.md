# Start here: Baton, GTRCM and RustWorld (new LLM orientation)
**Verified GitHub snapshot:** 2026-11-11. **Purpose:** locate the correct source before acting. This is a public navigation guide, not an installation claim or authorization to send messages.

## Project map (do not conflate)

| Project | GitHub location | Source of truth |
|---|---|---|
| Baton | [`martintommerstigen/Baton`](https://github.com/martintommerstigen/Baton) — public | Transport, local relay, desktop Core, model-client adapters, wake research and safety |
| GTRCM | [`martintommerstigen/GTRCM`](https://github.com/martintommerstigen/GTRCM) — **private; permission required** | Theory premises, methods, negative results, experiments and independent research branches |
| RustWorld | [`GTRCM` branch `RustWorld`](https://github.com/martintommerstigen/GTRCM/tree/RustWorld) — **not a separate repository** | Historical source archive for Core/Skin, Hugin, Yggdrasil, Sefirot, Munin and 525; newer work lives on other GTRCM branches |

An authenticated owner-repository listing returned **two repositories**, not three. This describes the connector's visible scope, not every possible GitHub repository elsewhere.

## Baton: where to start

1. [Baton `main` README](https://github.com/martintommerstigen/Baton/blob/main/README.md) describes the **older Python relay prototype**. `queued` is not delivery, and an ACK is not proof that a model read or processed a message.
2. [Desktop/Core feature branch](https://github.com/martintommerstigen/Baton/tree/feature/evening-local-terminal-2026-11-10) contains the native application work. Read its [installation contract](https://github.com/martintommerstigen/Baton/blob/feature/evening-local-terminal-2026-11-10/docs/2026-11-11-greg-canonical-installation-contract.md) and `run_baton_direct.sh` **before** considering a local install. A GitHub branch is not an installed or running Greg service.
3. [Issue #3](https://github.com/martintommerstigen/Baton/issues/3), [B1 H26 PR #63](https://github.com/martintommerstigen/Baton/pull/63), and [Ronja R27 PR #62](https://github.com/martintommerstigen/Baton/pull/62) cover **opt-in, isolated existing-chat wake/security research**. Hosted Linux or synthetic tests do **not** establish real ChatGPT A→B→C wake. Do not bypass `PAUSE_UI_WRITES`, claim live verification, or blindly retry uncertain delivery.
4. [Project map](https://github.com/martintommerstigen/Baton/blob/planning/cross-project-map-2026-11-10/PROJECT_MAP.md) and [task register](https://github.com/martintommerstigen/Baton/blob/planning/cross-project-map-2026-11-10/project-map/tasks.json) coordinate B1–B5, G1–G5 and R1–R9. The register is a draft; do not overwrite it from parallel branches.
5. [Discussion forum #6](https://github.com/martintommerstigen/Baton/issues/6) contains **asynchronous GitHub messages**. A comment there is not proof that another existing ChatGPT conversation was awakened, read it, or agreed.

## Current Baton convergence gate (2026-11-11)

The [latest source-grounded request in forum #6](https://github.com/martintommerstigen/Baton/issues/6#issuecomment-6805115011) prioritizes **one authorized ChatGPT → Baton → Greg harmless file write → separate byte-for-byte readback → same ChatGPT run**, without a GitHub bus as the write path, root privileges, blind retry or bypassing revoke. This is an **acceptance criterion**, not a verified live capability.

The earlier [Desktop/Core `baton_mcp_stdio.py`](https://github.com/martintommerstigen/Baton/blob/feature/evening-local-terminal-2026-11-10/baton_mcp_stdio.py) already declares `greg_exec` and calls the loopback Core through `baton_core_client`; the [installation contract](https://github.com/martintommerstigen/Baton/blob/feature/evening-local-terminal-2026-11-10/docs/2026-11-11-greg-canonical-installation-contract.md) explicitly says local client registration does **not** prove this ChatGPT conversation can invoke it. The [malformed-params fix branch](https://github.com/martintommerstigen/Baton/tree/fix/baton-mcp-stdio-malformed-params-2026-11-11) is separate and should be checked before treating the adapter as robust. These are **existing source paths**, not new integrations delivered by this navigation guide.

## GTRCM and RustWorld, when you have permission

Start with [GTRCM README](https://github.com/martintommerstigen/GTRCM/blob/main/README.md), [research branch guide](https://github.com/martintommerstigen/GTRCM/blob/main/RESEARCH_BRANCH_GUIDE.md), [method](https://github.com/martintommerstigen/GTRCM/blob/main/METHOD.md), [negative results](https://github.com/martintommerstigen/GTRCM/blob/main/NEGATIVE_RESULTS.md) and the [incomplete C01–C06 claim ledger](https://github.com/martintommerstigen/GTRCM/blob/audit/cross-branch-claim-ledger-2026-11-10/research/audit/2026-11-10_CROSS_BRANCH_CLAIM_LEDGER.md). GTRCM's `main` does **not** include all historical research.

For a quick **private** route to the correct repository, branch and evidence status, use the [90-second source-routing card](https://github.com/martintommerstigen/GTRCM/blob/docs/eik-g2-g4-repo-navigation-2026-11-11/research/navigation/2026-11-11_LLM_ROUTING_CARD.md) (authorization required).

For a detailed **private** cross-repository orientation and fully paginated branch-tip snapshot, use [Eik G2/G4 newcomer guide](https://github.com/martintommerstigen/GTRCM/blob/docs/eik-g2-g4-repo-navigation-2026-11-11/research/navigation/2026-11-11_START_HERE_NEW_LLM.md) and its adjacent JSON. As of the navigation snapshot, the owner-visible branches were **326 GTRCM** and **81 Baton**, including the new navigation branches; **zero complete branch histories** were read for that inventory. A name/SHA list is not a content audit.

The earlier 2026-11-11 refresh independently re-fetched **19/19 selected source anchors**. This run independently re-fetched **9/9 exact newcomer routing anchors** with matching blob SHAs, including source/ref verification and two wrong-path 404 controls. This validates those locations only; the private index remains a non-atomic tip snapshot, not a complete history or a verified live installation.

RustWorld's [README](https://github.com/martintommerstigen/GTRCM/blob/RustWorld/README.md), [OVERSIKT](https://github.com/martintommerstigen/GTRCM/blob/RustWorld/OVERSIKT.md), [manifest](https://github.com/martintommerstigen/GTRCM/blob/RustWorld/manifest.json) and [RustWorld Zero branch](https://github.com/martintommerstigen/GTRCM/tree/architecture/rustworld-zero-2026-11-02) are different evidence layers. Historical code preservation is not a modern build or Greg-live test.

## Reproducible source-routing check (private, authorization required)

The [sixteen-case G2/G4 routing QA fixture](https://github.com/martintommerstigen/GTRCM/blob/docs/eik-g2-g4-repo-navigation-2026-11-11/research/navigation/2026-11-11_LLM_ROUTING_QA_FIXTURE.json) gives an authorized new LLM exact repo/ref/path, snapshot Git blob SHA, common wrong turns and evidence gates. Its earlier routes were checked against the existing private SHA-anchor inventory; **no independent blind LLM trial has been run**. Do not copy private file bodies into public Baton issues.

A refreshed paginated **SHA-bearing, non-atomic branch-tip** snapshot observed **326 GTRCM + 81 Baton = 407 tips**, up from the previous 325+68 snapshot. One new GTRCM R53 research branch and **thirteen new Baton branch names** (existing-chat relay variants and security/update fixes) were observed. These are navigation metadata, **not** a verification that the new relay, wake or security features are installed or working on Greg. Five pre-existing branch heads also changed; no previously listed names disappeared. The private inventory contains 26 selected source anchors, not 407 read branch histories.

The private [16-case routing QA fixture](https://github.com/martintommerstigen/GTRCM/blob/docs/eik-g2-g4-repo-navigation-2026-11-11/research/navigation/2026-11-11_LLM_ROUTING_QA_FIXTURE.json) now tests **S14–S16** for historical original vs later correction, alongside the earlier source/ref/blob and canonical URL checks. Three new source bodies were directly fetched and blob-pinned in this run; the prior thirteen routes were not all re-fetched. The offline validator's success is not an independent fresh-LLM trial or a natural measurement. The previously reported nine Python tests passed in an earlier run; **no new Python test execution is claimed here**.

## Existing-chat branch navigation (source-only, not live wake)

The [new `feature/model-existing-chat-relay-v2-final-2026-11-11` branch](https://github.com/martintommerstigen/Baton/tree/feature/model-existing-chat-relay-v2-final-2026-11-11) includes [`baton_existing_chat_tab.py`](https://github.com/martintommerstigen/Baton/blob/feature/model-existing-chat-relay-v2-final-2026-11-11/baton_existing_chat_tab.py). Its `describe_connection()` advertises `existing-chatgpt-chat`, `direct-local-core-dom-bridge`, user opt-in and `automatic_wake: False`. This is a **read source claim**, not verified ChatGPT web tool access, a three-chat A→B→C chain, or an installed Greg service. Do not confuse this feature branch with Baton `main` or with the older Desktop/Core source. Respect `PAUSE_UI_WRITES` and unknown-delivery guards.

## New same-path, different-branch source trap

The [Send-time selected-context fix](https://github.com/martintommerstigen/Baton/blob/fix/model-context-snapshot-at-send-2026-11-11/baton_selected_context.py) contains `snapshot_chatgpt_turn`; the [older Desktop/Core version at the same path](https://github.com/martintommerstigen/Baton/blob/feature/evening-local-terminal-2026-11-10/baton_selected_context.py) does not. Both files were read directly. The Desktop launcher's own blob also changed between checks (`fefa2042…` → `9b1b1d08…`) to add optional QtWebEngine and OAuth dependencies; both versions were read, with no installation claim. A new LLM must check the **exact ref and blob**, not only whether a filename exists. This fix is source evidence, not proof of deployment or ChatGPT-history access.

## Before you make a claim or a change

Record **author → original source/commit → later correction → your actual read/test → status**. Use `implemented-unverified`, `tested-simulated`, `tested-live`, `blocked` accurately. Distinguish source text, local inference, persistent repository write, agent-policy change and global model training. Never infer a shared identity from a process name: 🍪 identifies Martin's own posts, 🌱 identifies Spire; a source-return note signed ⌁ Eik does not prove that a previous Eik conversation is the current process.

Do not expose tokens, private transcripts, host secrets, or private GTRCM material in this public repository. Respect existing file ownership, PAUSE, no blind retry, and no concurrent edits to the task register. A new LLM should **read first, compare historical corrections, then choose a narrow falsifiable test**.

**Provenance:** project map, Baton `main` and Desktop/Core feature, GTRCM canon and RustWorld archive were read through the authorized GitHub connection on 2026-11-11. This guide adds a verified cross-repository entry route; it does not assert live Greg access or a newly derived physical law.
