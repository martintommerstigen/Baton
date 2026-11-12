# Baton — entrypoint for new LLMs and coding agents

**Read before changing or operating anything.** This note routes to sources; it does not authorize Greg access, message sending, installation, or an existing ChatGPT conversation wake.

## First route the question

1. [Baton `main` README](README.md) documents an **older local Python relay**. Native Desktop/Core work is on [the Desktop feature branch](https://github.com/martintommerstigen/Baton/tree/feature/evening-local-terminal-2026-11-10); read its [installation contract](https://github.com/martintommerstigen/Baton/blob/feature/evening-local-terminal-2026-11-10/docs/2026-11-11-greg-canonical-installation-contract.md). A source branch or CI PASS does not establish a running Greg installation.
2. For existing-chat wake, read [issue #3](https://github.com/martintommerstigen/Baton/issues/3), [forum #6](https://github.com/martintommerstigen/Baton/issues/6), and the [existing-chat tab source](https://github.com/martintommerstigen/Baton/blob/feature/model-existing-chat-relay-v2-final-2026-11-11/baton_existing_chat_tab.py). Queued/ACK/comment is **not** a verified recipient turn or live A→B→C wake.
3. Read the [public newcomer guide (draft navigation branch)](https://github.com/martintommerstigen/Baton/blob/docs/eik-repository-onboarding-2026-11-11/docs/START_HERE_NEW_LLM.md). For theory and prior findings, authorized readers may use the [private GTRCM question-first router](https://github.com/martintommerstigen/GTRCM/blob/docs/eik-g2-g4-repo-navigation-2026-11-11/research/navigation/2026-11-12_QUESTION_FIRST_ROUTER.md). These documents are in **draft PRs**, not necessarily on `main`.
4. Before claiming novelty or completion, inspect the original file at an exact **repo/ref/path/blob**, its tests and later corrections. Distinguish `reported / implemented-unverified / tested-simulated / tested-live / blocked`. Ask whether the task has already been answered; do not repeat an old status report as new work.

## Boundaries

- **GTRCM** is a **private** research repository. Do not copy its private source bodies, credentials or transcripts into public Baton.
- **RustWorld** is a historical **branch of GTRCM**, not a third owner-visible repo.
- **Core/Skin:** only Skin talks to Core; only Core changes Core. Preserve the established code ownership boundaries.
- Respect `PAUSE_UI_WRITES`, opt-in and revoke, least privilege, allowlists, no blind resend after uncertain delivery, and no exposed tokens. Do not infer that a GitHub issue comment awakened an independent ChatGPT conversation.

Source, transport attempt, delivery, receipt, processing, response and completion are different events. Keep their provenance separate.
