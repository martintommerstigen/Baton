# Start here — Baton, GTRCM and RustWorld

**For a new LLM with no inherited chat context.** This is a navigation map, not permission to operate Greg, send messages or claim an existing ChatGPT conversation was awakened. **Read the original before answering.**

## First 60 seconds

1. Identify the user's actual question: **theory / RustWorld / Baton code / installed system / historical priority**. Do not read branch names sequentially.
2. Open the source in the correct repository and **exact ref + path**. Check the Git blob SHA if provenance matters. A filename on another branch may have different behavior.
3. Read an **older original** and any **later correction or negative control** before calling something new.
4. State evidence accurately: `reported`, `implemented-unverified`, `tested-simulated`, `tested-live`, or `blocked`. A CI pass, issue comment or ACK does not prove a live ChatGPT receiver turn.
5. Answer the specific question, not another repository inventory. If the previous answer already covered it, report only a verified change.

## Where to go

| Your question | Open first | Avoid this mistake |
|---|---|---|
| What does GTRCM assume, and what has it *not* derived? | [GTRCM canonical program](https://github.com/martintommerstigen/GTRCM/blob/main/GTRCM_KANONISK_GRUNNPROGRAM.md), [method](https://github.com/martintommerstigen/GTRCM/blob/main/METHOD.md), [negative results](https://github.com/martintommerstigen/GTRCM/blob/main/NEGATIVE_RESULTS.md), [open problems](https://github.com/martintommerstigen/GTRCM/blob/main/OPEN_PROBLEMS.md) | Private repo; permission required. Model demonstrations are not physical predictions. |
| Has a research claim already been made or corrected? | [Private question-first router](https://github.com/martintommerstigen/GTRCM/blob/docs/eik-g2-g4-repo-navigation-2026-11-11/research/navigation/2026-11-12_QUESTION_FIRST_ROUTER.md) and [source-routing fixture](https://github.com/martintommerstigen/GTRCM/blob/docs/eik-g2-g4-repo-navigation-2026-11-11/research/navigation/2026-11-11_LLM_ROUTING_QA_FIXTURE.json) | Latest synthesis is not necessarily earliest original. The fixture is a source-location check, not a new-LLM trial. |
| Where is RustWorld, Hugin, 525, Yggdrasil, Sefirot, Munin? | [GTRCM `RustWorld` branch](https://github.com/martintommerstigen/GTRCM/tree/RustWorld) and [RustWorld Zero](https://github.com/martintommerstigen/GTRCM/tree/architecture/rustworld-zero-2026-11-02) | RustWorld is a **historical branch**, not a third owner-visible repository; source does not prove installation. |
| Where is Baton Desktop/Core? | [Desktop feature branch](https://github.com/martintommerstigen/Baton/tree/feature/evening-local-terminal-2026-11-10) and [Greg installation contract](https://github.com/martintommerstigen/Baton/blob/feature/evening-local-terminal-2026-11-10/docs/2026-11-11-greg-canonical-installation-contract.md) | Baton `main` [README](https://github.com/martintommerstigen/Baton/blob/main/README.md) describes an older relay. |
| Can Baton wake an **existing** ChatGPT conversation? | [Issue #3](https://github.com/martintommerstigen/Baton/issues/3), [existing-chat tab source](https://github.com/martintommerstigen/Baton/blob/feature/model-existing-chat-relay-v2-final-2026-11-11/baton_existing_chat_tab.py), [forum #6](https://github.com/martintommerstigen/Baton/issues/6) | Queued/ACK/forum ≠ observed recipient turn. Respect opt-in, revoke and `PAUSE_UI_WRITES`. |
| Which existing-chat UI source is current: Brave or embedded? | [v2-final existing-chat tab](https://github.com/martintommerstigen/Baton/blob/feature/model-existing-chat-relay-v2-final-2026-11-11/baton_existing_chat_tab.py) versus [older v1 tab](https://github.com/martintommerstigen/Baton/blob/feature/model-existing-chat-relay-v1-2026-11-11/baton_existing_chat_tab.py) | v2-final prefers Brave/Chromium Native Messaging, with embedded QtWebEngine as fallback. Source does not prove installed bridge, automatic wake, or verified recipient turn. |
| Which code provides remote MCP access to Greg Core? | [Core-gated loopback adapter](https://github.com/martintommerstigen/Baton/blob/fix/remote-mcp-core-boundary-2026-11-11/baton_remote_mcp.py) versus [main's legacy queue relay](https://github.com/martintommerstigen/Baton/blob/main/server.py) | MCP adapter requires strong token, non-root, active Baton UI lease and authenticated HTTPS proxy for remote access; 127.0.0.1 listener is not a public service. No Greg deployment verified. |
| Which selected-context implementation runs at Send time? | [Send-time fix](https://github.com/martintommerstigen/Baton/blob/fix/model-context-snapshot-at-send-2026-11-11/baton_selected_context.py) versus [older same-path file](https://github.com/martintommerstigen/Baton/blob/feature/evening-local-terminal-2026-11-10/baton_selected_context.py) | Both paths exist; only the former has the relevant Send-time snapshot implementation. |

## Repository scope and verification

An authenticated owner-affiliation listing on **12 November 2026** found **two repositories**: public [Baton](https://github.com/martintommerstigen/Baton) and private [GTRCM](https://github.com/martintommerstigen/GTRCM). A paginated, **non-atomic** branch-tip snapshot exists; its counts are dated and are **not** counts of fully read histories. For current numbers consult the [private SHA-bearing inventory](https://github.com/martintommerstigen/GTRCM/blob/docs/eik-g2-g4-repo-navigation-2026-11-11/research/navigation/2026-11-11_EIK_OWNER_REPOS_AND_BRANCH_TIPS.json) is a dated snapshot and will become stale.

The [private source-routing fixture (consult `grading.denominator`; S35/S36 cover the Baton distinctions above)](https://github.com/martintommerstigen/GTRCM/blob/docs/eik-g2-g4-repo-navigation-2026-11-11/research/navigation/2026-11-11_LLM_ROUTING_QA_FIXTURE.json) checks selected original-versus-correction traps, including the R60→R61→R62 correction. **R60 correction:** R61 shows that the R60 holdout cannot certify independent profiles; R62's cross-witness recovery requires additional same-shot independent references. This is a private GTRCM source route, not evidence of nature or a Baton deployment.

**No independent blind fresh-LLM A/B trial** or Greg-live write/readback is established by this documentation. Do not copy private GTRCM source bodies, transcripts, tokens or secrets into this public repo.

## Operating boundaries

Only Skin talks to Core; only Core changes Core. Keep source, transport attempt, delivery, receipt, processing, response and completion as **separate evidence events**. No blind resend after uncertain delivery, no privilege escalation, no invented authorization, no bypass of `PAUSE_UI_WRITES`.

**For historical detail:** [previous extended navigation log at a pinned commit](https://github.com/martintommerstigen/Baton/blob/c4f6294beb6fc9f6aca176ef6df4a578f9134855/docs/START_HERE_NEW_LLM.md). That log contains dated counts and past checks; it is not the current quickstart. The detailed navigation improvements remain in [draft PR #65](https://github.com/martintommerstigen/Baton/pull/65), not necessarily merged into `main`.
