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

## GTRCM and RustWorld, when you have permission

Start with [GTRCM README](https://github.com/martintommerstigen/GTRCM/blob/main/README.md), [research branch guide](https://github.com/martintommerstigen/GTRCM/blob/main/RESEARCH_BRANCH_GUIDE.md), [method](https://github.com/martintommerstigen/GTRCM/blob/main/METHOD.md), [negative results](https://github.com/martintommerstigen/GTRCM/blob/main/NEGATIVE_RESULTS.md) and the [incomplete C01–C06 claim ledger](https://github.com/martintommerstigen/GTRCM/blob/audit/cross-branch-claim-ledger-2026-11-10/research/audit/2026-11-10_CROSS_BRANCH_CLAIM_LEDGER.md). GTRCM's `main` does **not** include all historical research.

For a detailed **private** cross-repository orientation and fully paginated branch-tip snapshot, use [Eik G2/G4 newcomer guide](https://github.com/martintommerstigen/GTRCM/blob/docs/eik-g2-g4-repo-navigation-2026-11-11/research/navigation/2026-11-11_START_HERE_NEW_LLM.md) and its adjacent JSON. As of the navigation snapshot, the owner-visible branches were **320 GTRCM** and **64 Baton**, including the new navigation branches; **zero complete branch histories** were read for that inventory. A name/SHA list is not a content audit.

The 2026-11-11 refresh independently re-fetched **17/17 selected source anchors** with matching blob SHAs and observed one additional GTRCM research branch. This validates those locations only; the private index remains a non-atomic tip snapshot, not a complete history or a verified live installation.

RustWorld's [README](https://github.com/martintommerstigen/GTRCM/blob/RustWorld/README.md), [OVERSIKT](https://github.com/martintommerstigen/GTRCM/blob/RustWorld/OVERSIKT.md), [manifest](https://github.com/martintommerstigen/GTRCM/blob/RustWorld/manifest.json) and [RustWorld Zero branch](https://github.com/martintommerstigen/GTRCM/tree/architecture/rustworld-zero-2026-11-02) are different evidence layers. Historical code preservation is not a modern build or Greg-live test.

## Before you make a claim or a change

Record **author → original source/commit → later correction → your actual read/test → status**. Use `implemented-unverified`, `tested-simulated`, `tested-live`, `blocked` accurately. Distinguish source text, local inference, persistent repository write, agent-policy change and global model training. Never infer a shared identity from a process name: 🍪 identifies Martin's own posts, 🌱 identifies Spire; a source-return note signed ⌁ Eik does not prove that a previous Eik conversation is the current process.

Do not expose tokens, private transcripts, host secrets, or private GTRCM material in this public repository. Respect existing file ownership, PAUSE, no blind retry, and no concurrent edits to the task register. A new LLM should **read first, compare historical corrections, then choose a narrow falsifiable test**.

**Provenance:** project map, Baton `main` and Desktop/Core feature, GTRCM canon and RustWorld archive were read through the authorized GitHub connection on 2026-11-11. This guide adds a verified cross-repository entry route; it does not assert live Greg access or a newly derived physical law.
