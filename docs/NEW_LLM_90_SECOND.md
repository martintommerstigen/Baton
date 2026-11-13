# Baton — 90-second route for a new LLM

**Start with the question. Do not assume an inbound message grants an outbound tool or permission to operate Greg.**

| Need | Read | Important limit |
| --- | --- | --- |
| What is on `main`? | [README](../README.md), [legacy relay](../server.py) | The legacy relay is not the Desktop/Core installation |
| Where is the current Desktop/Core source? | [Desktop branch](https://github.com/martintommerstigen/Baton/tree/feature/evening-local-terminal-2026-11-10), [installation contract](https://github.com/martintommerstigen/Baton/blob/feature/evening-local-terminal-2026-11-10/docs/2026-11-11-greg-canonical-installation-contract.md) | Source and CI do not prove the installed Greg version |
| How do existing chats communicate? | [Existing-chat v2](https://github.com/martintommerstigen/Baton/blob/feature/model-existing-chat-relay-v2-final-2026-11-11/baton_existing_chat_tab.py), [onboarding](https://github.com/martintommerstigen/Baton/blob/feature/agent-discovery-onboarding-2026-11-13/baton_agent_onboarding.py) | Invitation/ACK is not a verified live recipient model turn |
| What safety corrections matter? | [PR #83](https://github.com/martintommerstigen/Baton/pull/83) → [#88](https://github.com/martintommerstigen/Baton/pull/88) → [#91](https://github.com/martintommerstigen/Baton/pull/91) | Pause, empty-turn adjacency and Stop/re-arm are distinct hazards; drafts not installed |
| How do peers review and disagree? | [PR #85](https://github.com/martintommerstigen/Baton/pull/85) → [#92](https://github.com/martintommerstigen/Baton/pull/92) → [#93](https://github.com/martintommerstigen/Baton/pull/93) | Preserve source-bound parallel verdicts; do not invent reviewer authority |
| Where are all Baton PRs? | [Dated 89-PR lifecycle index](https://github.com/martintommerstigen/Baton/blob/docs/eik-repository-onboarding-2026-11-11/docs/2026-11-12_BATON_PR_LIFECYCLE_INDEX.json) | 93 branch heads; snapshot, not live status |

Before claiming a discovery, check the original, the later correction and a negative test. Record repo/ref/path/blob SHA and distinguish `reported`, `tested-simulated` and `tested-live`. Respect `PAUSE_UI_WRITES`, explicit consent, revocation and no blind resend. Only Skin talks to Core; only Core changes Core. Baton is public; never copy private GTRCM bodies or personal transcripts here.

[Longer task-specific navigation](../START_HERE.md).
