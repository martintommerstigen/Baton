# Ronja R27 — four preconnected B1 observer sessions (B5/B2)

2026-11-11. **Draft, do not deploy.** Bounded Linux capability and one-shot protocol implementation; not real existing-ChatGPT A→B→C, Greg installation, or ChatGPT authorship attestation.

## Source gate and precise delta

- [Issue #3](https://github.com/martintommerstigen/Baton/issues/3) requires three **existing** ChatGPT conversation IDs and fresh assistant turn IDs, not SIWC/forum. [PR #4](https://github.com/martintommerstigen/Baton/pull/4) is an offline UI/ledger experiment.
- [B1 H24 original](https://github.com/martintommerstigen/Baton/blob/feature/b1-r25-lifetime-enforcement-2026-11-11/b1_snapshot_relay.py) calls **three** one-shot source snapshots (two before witness, one after) and **one** one-shot witness. It rechecks R24 before each request.
- [R25](https://github.com/martintommerstigen/Baton/pull/58) establishes persistent seccomp; [R26](https://github.com/martintommerstigen/Baton/pull/60) seals **one** stream. [R23](https://github.com/martintommerstigen/Baton/blob/research/ronja-r26-sealed-unix-channel-2026-11-11/remote_security/frame_credentials.py) authenticates per-frame sender UID at the server.
- **R27 difference:** preconnect exactly **three collector streams plus one broker witness stream**, verify separate kernel UIDs, reject undeclared FDs, require R25 kernel effects, then apply R26 irreversible syscall-denial filter. B1-compatible snapshot/witness callbacks enforce snapshot → snapshot → witness → snapshot. Each socket is spent before possible transmission. Ambiguous witness delivery is terminal, never blindly retried.
- **Negative discovered in local prototype:** direct indexing by protocol stage routed witness stage 2 to snapshot FD 2. Fixed by mapping (0,1,3,2) and cross-UID tests. First GitHub CI [43033500858](https://github.com/martintommerstigen/Baton/actions/runs/43033500858) **FAILED 4 PASS/3 FAIL** because R26 ChannelSealDenied escaped R27 SessionSealDenied; the adapter now normalizes that error without relaxing any kernel policy.
- **Not integrated into B1 runner:** H24 repeated R24 preflight opens fresh sockets and would fail after sealing. B1 must approve a separate opt-in entry that performs R24 before preconnection, then relies on the persistent R25/R27 boundary. R27 never edits B1-owned files or disables PAUSE_UI_WRITES. Collector/witness must still independently enforce R23, allowlists, digest binding and durable R22 SQLite.

## GTRCM/RustWorld historical difference

Read [C01–C06](https://github.com/martintommerstigen/GTRCM/blob/audit/cross-branch-claim-ledger-2026-11-10/research/audit/2026-11-10_CROSS_BRANCH_CLAIM_LEDGER.md), [Kaja 19 Oct](https://github.com/martintommerstigen/GTRCM/blob/kaja/gtrcm-proof-roadmap-2026-10-19/research/2026-10-19-kaja-dynamic-observability.md), [main NEG](https://github.com/martintommerstigen/GTRCM/blob/main/NEGATIVE_RESULTS.md), [Rolf O/K/I](https://github.com/martintommerstigen/GTRCM/blob/research/rolf-operative-memory-rustworld-2026-11-10/research/rolf/2026-11-10_OPERATIVE_MEMORY_OBSERVATION_RUSTWORLD.md), [RustWorld preservation overview](https://github.com/martintommerstigen/GTRCM/blob/RustWorld/OVERSIKT.md), and excerpts from [Eik C36](https://github.com/martintommerstigen/GTRCM/blob/research/eik-c36-hidden-intermediate-priority-2026-11-11/research/eik/corpus/2026-11-11_G2_G4_C36_HIDDEN_INTERMEDIATE_PRIORITY.md) and [Vanja R45](https://github.com/martintommerstigen/GTRCM/blob/research/vanja-r45-hidden-sector-and-gravity-gates-2026-11-11/research/vanja/r45/2026-11-11_C61_C63_HIDDEN_SECTOR_GRAVITY_CALIBRATION_GATES.md).

**Claim B5-RJ20:** socket peer UID, self-reported snapshot, and verified existing ChatGPT assistant turn are **three distinct claims**. R27 is a new bounded application of established Linux/R24–R26 and C06 source/access distinctions, **not new GTRCM physics**. Falsifiers: undeclared FD, wrong-role UID, changed payload, replay or uncertain witness response that permits another send.

[316-tip paginated SHA inventory](2026-11-11-r27-gtrcm-branch-tips-316.json): 100+100+100+16+0; **0/316 complete branch histories**. Seven selected original GTRCM source files read fully or as excerpts, explicitly marked. Tip dates, themes, documents null where not checked. No Greg/Mac/private conversation access.

## Test evidence and next gate

Local isolated Linux prototype: actual separate UIDs/seccomp and synthetic R25-equivalent; nine tests passed, but **not byte-identical to GitHub R27**. Dedicated [R27 workflow](../../.github/workflows/ronja-r27-four-session.yml) runs seven cross-UID tests with actual pinned R25+R26. Check the post-fix workflow receipt separately; do not assume success from a code commit.

Not tested-live: Greg, CDP, RustWorld launcher, 525 on Mac/iPhone, A→B→C. No Desktop Commander, credentials, UI Send or external posts.

**Next integration:** B1-owned opt-in entry performs R24 before opening sockets, installs R25, preconnects 3+1 role-separated streams, seals R27, calls B1 observe_via_snapshots with the sealed callbacks, then verifies R22 SQLite uncertainty/restart without replay. Keep the current B1 runner unchanged until this contract passes. A real Greg CDP isolation test remains required.
