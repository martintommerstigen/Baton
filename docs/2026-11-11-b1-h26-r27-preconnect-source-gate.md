# B1/B5 H26 — R27 preconnected source observer (2026-11-11)

**Scope:** separate opt-in B1 entry, no UI Send, no remote shell, no ChatGPT authentication claim. Stack: H25 PR #61 over H24 PR #59. Ronja R27 stays in [her PR #62](https://github.com/martintommerstigen/Baton/pull/62); pinned dependency commit `0f6935461e8a40e143f9497ce792dcc18bc10f9c`. This document does not update the shared project-map register.

## Source gate / precedence

| Source | Original / branch | Evidence read this run | Relevance and limit |
|---|---|---|---|
| GTRCM C01–C06 | [cross-branch ledger](https://github.com/martintommerstigen/GTRCM/blob/audit/cross-branch-claim-ledger-2026-11-10/research/audit/2026-11-10_CROSS_BRANCH_CLAIM_LEDGER.md) | Full document | C06 already distinguishes source, access, calibration, provenance; no new physics claim |
| Kaja 19 Oct | [dynamic observability](https://github.com/martintommerstigen/GTRCM/blob/kaja/gtrcm-proof-roadmap-2026-10-19/research/2026-10-19-kaja-dynamic-observability.md) | Original file content | More observations need not imply persistent closure |
| Egil R76 | [contact surface](https://github.com/martintommerstigen/GTRCM/blob/research/egil-r77-gtrcm-coinductive-individuation-2026-11-05/research/egil/2026-11-05_EGIL_R76_KONTAKTFLATE_FYSISK_OVERSETTELSE.md) | Original file content | Changing contact/access is not a mere inference over same transcript |
| Riss R20 | [existing-chat exchanges](https://github.com/martintommerstigen/GTRCM/blob/research/riss-r20-multichat-learning-2026-11-07/research/riss/2026-11-07_RISS_R20_FLERE_CHATTER_LAERER_HVERANDRE.md) | Original file content | Historical actual sends; no proven independent Lodd→Vev; UI lock released early |
| Rolf 10 Nov | [O/K/I](https://github.com/martintommerstigen/GTRCM/blob/research/rolf-operative-memory-rustworld-2026-11-10/research/rolf/2026-11-10_OPERATIVE_MEMORY_OBSERVATION_RUSTWORLD.md) | Original file content | O does not imply K; K does not imply persistent I |
| RustWorld | [README](https://github.com/martintommerstigen/GTRCM/blob/RustWorld/README.md) and [OVERSIKT](https://github.com/martintommerstigen/GTRCM/blob/RustWorld/OVERSIKT.md) | Both original file contents | Preserved source is not live 525/Core/Skin verification |
| GTRCM main | [NEGATIVE_RESULTS](https://github.com/martintommerstigen/GTRCM/blob/main/NEGATIVE_RESULTS.md) | Original content | No source-to-inertia shortcut; not changed |
| Baton B1 | [issue #3](https://github.com/martintommerstigen/Baton/issues/3), [PR #4](https://github.com/martintommerstigen/Baton/pull/4), [H24 entry](https://github.com/martintommerstigen/Baton/blob/feature/b1-r25-lifetime-enforcement-2026-11-11/run_b1_snapshot_observer.py), [B1 relay](https://github.com/martintommerstigen/Baton/blob/feature/b1-r25-lifetime-enforcement-2026-11-11/b1_snapshot_relay.py) | Acceptance and code read | Repeated R24 checks opened sockets; incompatible with R26/R27 post-connect sealing |
| Baton B5 | [R24 original](https://github.com/martintommerstigen/Baton/blob/research/ronja-r27-four-session-seal-2026-11-11/remote_security/observer_boundary.py), [R26](https://github.com/martintommerstigen/Baton/blob/research/ronja-r27-four-session-seal-2026-11-11/remote_security/sealed_unix_channel.py), [R27](https://github.com/martintommerstigen/Baton/blob/research/ronja-r27-four-session-seal-2026-11-11/remote_security/sealed_observer_sessions.py), [R27 tests](https://github.com/martintommerstigen/Baton/blob/research/ronja-r27-four-session-seal-2026-11-11/tests/test_sealed_observer_sessions.py) | Original source and negative tests read | Four preconnected streams, kernel UID and seccomp already implemented by Ronja |
| Coordination | [project map](https://github.com/martintommerstigen/Baton/blob/planning/cross-project-map-2026-11-10/PROJECT_MAP.md), [forum #6](https://github.com/martintommerstigen/Baton/issues/6) | Map and latest comments read | B1 owns orchestration, B5 owns kernel modules |

**Measured coverage:** [317 paginated branch-tip names and SHA values](b1/2026-11-11-gtrcm-branch-tips-317-h26.json), pages 100+100+100+17+0 on 11 Nov; **0/317 complete branch histories**. The above is a selected original-file inspection, not a claim that all branches or conversations were read. Tip dates/themes and full document indexes remain unknown. Greg, Mac, private chat history and installed `PAUSE_UI_WRITES` not accessible. The cited original GTRCM texts are a source sample, not evidence of global novelty.

## Concrete delta from R27 and H24

**Already done:** R27 has four role-pinned AF_UNIX streams and one-use snapshot→snapshot→witness→snapshot ordering. H24 had R24 preflight before *each* request and R25 lifetime restrictions, which conflicts with R27's irreversible denial of new sockets.

**H26 change:** a separate opt-in source-only entry validates exact B1 request, checks PAUSE, installs R25, runs R24 *once before any preconnection*, validates both socket paths, preconnects three collector streams and one broker witness stream, applies Ronja R27, and calls B1's existing `observe_via_snapshots` using R27's callbacks. R27 controls peer UIDs, FD inventory, strict ordering, payload and uncertainty; B1 preserves its source/witness rechecks. No new transport protocol, CDP write, UI Send or R22 schema change. No Ronja-owned source file modified.

**Threat / negative controls:** missing R25 or R24, wrong role UID, wrong payload digest, active/ambiguous pause, wrong endpoint, extra socket, seal failure, changed pause, uncertain witness disconnect, duplicate witness and post-seal socket creation. The R27 tests are pinned; H26 adds an actual B1→R27 kernel integration test with synthetic source and a separate ten-case orchestration test. A verified source snapshot is still *not* ChatGPT authorship, an authorized UI Send, or an existing-chat assistant reply.

**Important limitation:** The new integration harness uses a synthetic positive R24 preflight receipt to isolate the four-UID R27+B1 integration. It does **not** establish Greg's CDP/profile isolation. R24 itself is separately tested in its own branch. A real R24 pass, R22 SQLite persistence/restart and genuine A→B→C turn receipts are still required before any live claim.

## Reuse and license

[Baton LICENSE](https://github.com/martintommerstigen/Baton/blob/feature/b1-h25-legacy-next-digest-gate-2026-11-11/LICENSE) is Apache-2.0. R27 code is reused by pinned checkout from the same repository rather than copied into B1's source ownership. Python standard library only for H26 code; the pinned kernel filter uses the host's `libseccomp.so.2` and requires its system package and license to be checked before distribution. No OpenSSH/WireGuard implementation or third-party code is copied into H26. No public shell or token storage.

## Evidence / state

- Local isolated stubbed B1 orchestration: **10/10 PASS** (not a test of GitHub's exact B1 imports or live Linux policy).
- GitHub H26 workflow: initial [CI 43038549860](https://github.com/martintommerstigen/Baton/actions/runs/43038549860) failed because the test fixture omitted inherited cleanup; later [CI 43039109029](https://github.com/martintommerstigen/Baton/actions/runs/43039109029) failed at compile due to a literal escaped newline in a Python import. Both are retained as negative test/development evidence; final CI must be checked separately.
- Existing R27 baseline: [Ronja CI 43034035940](https://github.com/martintommerstigen/Baton/actions/runs/43034035940), 11/11 actual Linux cross-UID kernel tests; these are not H26 results.
- **B1/B5 H26 classification:** implemented-unverified until exact pinned CI completes; later at most tested-simulated.
- **A→B→C:** blocked. No Greg, CDP, actual ChatGPT assistant turn IDs, authorized Send, or 525 connection observed.

**Next direct action:** run the H26 pinned workflow and fix any actual CI failure. Then obtain a read-only, authorized Greg host manifest, verify R24/R25/R27 and `PAUSE_UI_WRITES`, test forced witness disconnect against actual R22 SQLite across restart, and only then seek an authorized existing-chat A→B→C attempt. No blind retry.
