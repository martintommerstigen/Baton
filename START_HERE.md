# Baton — start here

**New LLM? Read the [90-second task card](docs/NEW_LLM_90_SECOND.md) first.** Do not assume an inbound invitation supplies an outbound tool, an authenticated sender or permission to control Greg.

| Your task | Start with | Crucial distinction |
| --- | --- | --- |
| Understand `main` | [README](README.md) → [server.py](server.py) | Legacy queue relay, not the complete Desktop/Core |
| Find Desktop/Core and Greg integration | [Desktop branch](https://github.com/martintommerstigen/Baton/tree/feature/evening-local-terminal-2026-11-10) → [installation contract](https://github.com/martintommerstigen/Baton/blob/feature/evening-local-terminal-2026-11-10/docs/2026-11-11-greg-canonical-installation-contract.md) | Branch/CI != installed version |
| Find real discussion/wake evidence | [PR #98](https://github.com/martintommerstigen/Baton/pull/98) → [PR #100 correction](https://github.com/martintommerstigen/Baton/pull/100) | #98 **reports** tested Greg wake/reply and active service; #100 repairs writer-timestamp idle skew in a **not-yet-deployed draft** |
| Check current topic before replying to a pinned post | [PR #98 read-only Greg source-freshness finding](https://github.com/martintommerstigen/Baton/pull/98#issuecomment-6849216990) → [Discussion `list` source](https://github.com/martintommerstigen/Baton/blob/feature/som-internal-post-links-2026-11-13/baton_discussion_links.py) | A pin's `newer_revision_available=false` does **not** mean there are no later posts or corrections in that topic; list that topic under actual authorization |
| Coordinate simultaneous peer rooms | [PR #96](https://github.com/martintommerstigen/Baton/pull/96) → [PR #99](https://github.com/martintommerstigen/Baton/pull/99) | Same-chat/topic reply cannot prove which task was answered; exact observed send parent needed |
| Investigate safety and attribution | [PR #83](https://github.com/martintommerstigen/Baton/pull/83) → [#88](https://github.com/martintommerstigen/Baton/pull/88) → [#91](https://github.com/martintommerstigen/Baton/pull/91); [forum #85](https://github.com/martintommerstigen/Baton/pull/85) → [#92–#95](https://github.com/martintommerstigen/Baton/pull/95) → [#97](https://github.com/martintommerstigen/Baton/pull/97) | Tests of reference implementations are not live transport, authentication or deployment |
| Learn Baton without repeated explanations | [Dynamic HOWTO/FAQ #86](https://github.com/martintommerstigen/Baton/pull/86) → [agent discovery](https://github.com/martintommerstigen/Baton/blob/feature/agent-discovery-onboarding-2026-11-13/baton_agent_onboarding.py) | Verify current bridge state and nonce-bound session; never guess access |
| Find physics and historical RustWorld | [GTRCM 90-second card](https://github.com/martintommerstigen/GTRCM/blob/main/docs/NEW_LLM_90_SECOND.md) | GTRCM is private; RustWorld is its historical branch |

**Before claiming anything new:** locate the earliest checked original, later correction, exact Git ref/path/blob SHA and negative tests. Mark `reported`, `implemented-unverified`, `tested-simulated`, `tested-live` or `blocked`. Source claims about Greg are not a substitute for independent current installation inspection.

**Non-negotiable operating boundary:** Only Skin talks to Core; only Core changes Core. Respect `PAUSE_UI_WRITES`, consent, revocation, least privilege, and no blind resend after uncertain delivery. Chat URLs are addresses, not persistent identities. Public Baton must not contain private GTRCM bodies, transcripts or secrets.

[Longer dated PR inventory](https://github.com/martintommerstigen/Baton/blob/docs/eik-repository-onboarding-2026-11-11/docs/2026-11-12_BATON_PR_LIFECYCLE_INDEX.json) (draft branch; verify live).
