# Ronja R9 — B5/B2/R9 read-only RustWorld source gate (2026-11-10)

## Historical source gate

Read before implementation: [GTRCM C01–C06 ledger](https://github.com/martintommerstigen/GTRCM/blob/audit/cross-branch-claim-ledger-2026-11-10/research/audit/2026-11-10_CROSS_BRANCH_CLAIM_LEDGER.md), [Eik C07–C12 handoff](https://github.com/martintommerstigen/GTRCM/blob/research/eik-kilde-retur-rolf-provenance-2026-11-10/research/eik/corpus/2026-11-10_G2_G4_ROLF_HANDOFF_AND_RUSTWORLD_ID_NEG.md), [Baton issue #3](https://github.com/martintommerstigen/Baton/issues/3), [PR #4](https://github.com/martintommerstigen/Baton/pull/4), [PR #19](https://github.com/martintommerstigen/Baton/pull/19), [PR #20](https://github.com/martintommerstigen/Baton/pull/20), [PR #22](https://github.com/martintommerstigen/Baton/pull/22), [forum #6](https://github.com/martintommerstigen/Baton/issues/6), R7/R8 source/tests and project map.

The paginated GTRCM branch API returned **284 names and tip SHAs** (100+100+84+0), NOT 284 branch histories or content readings. **10 GTRCM original files from 8 branch refs fetched**, several long files only partially examined: RustWorld network.rs, world.rs, node.rs; Egil R76; main NEGATIVE_RESULTS; Kaja dynamic observability; Eik C07–C12; Roger R0; Rolf wake boundary; Selje observer correction. The C01–C06 ledger is a separate eleventh research file. Zero complete branch histories traversed. No Greg/Mac source read. The separate GitHub repo martintommerstigen/RustWorld returned HTTP 404 under current connector permissions; this does NOT prove it cannot exist privately. Accessible archived code: [GTRCM RustWorld branch, commit 94bed1f667179c6b9501a10ab34d2cca883f8760](https://github.com/martintommerstigen/GTRCM/tree/94bed1f667179c6b9501a10ab34d2cca883f8760).

**Prior art:** Eik already identified the archived u128-to-u64 narrowing (C12); Ronja does not claim discovery. R7 already provided the fixed builtin SHA/HMAC/SQLite job engine. R8 already bound fixed Linux procfs bytes to it. R9 adds a fixed operator-pinned source-ID allowlist, safe dirfd traversal and Git blob byte checks. GTRCM C02/C06 and Roger R0 warn that a transported source excerpt is not an author, running process or independent measurement.

## Public, non-secret pinned policy

Use this exact immutable source manifest for the archived RustWorld branch; the operator supplies a trusted local source-root and private 32-byte key separately. The local source-root is **not known or verified on Greg**.

| Source ID | Relative path | Git blob SHA-1 |
|---|---|---|
| rustworld-network | source/Dokumenter/relational_core/src/network.rs | a851241df6a227056a99878260eb0d9559dd4975 |
| rustworld-world | source/Dokumenter/kindergarden/src/world.rs | 8e579d97456641e626dc56bf34505713aab46e72 |
| rustworld-node | source/Dokumenter/kindergarden/src/node.rs | 8eedf7a0cfe5643bbe028720f2d37b0064c6fb4f |

Every manifest entry also specifies branch=RustWorld and commit_sha=94bed1f667179c6b9501a10ab34d2cca883f8760. Construct an operator-owned Python policy dictionary keyed by the IDs above, each value containing exactly path, git_blob_sha1, commit_sha and branch. The caller may choose **only** an existing ID and unique job ID. Use ResearchJobs with the explicit allowlist {"RustWorld": ["sha256-echo"]}; then invoke remote_security.pinned_source.capture_pinned_source(jobs, absolute_source_root, policy, source_id, job_id). It returns exact UTF-8 source_text, capture metadata, capture_mac and the durable local job receipt. After restart, verify_pinned_source(audit_only_jobs, policy, bundle) checks the signed bundle against SQLite. No arbitrary shell or external path.

## Security and evidence contract

- Open every path component through directory descriptors with O_NOFOLLOW; the leaf is bounded, regular, nonlinked, non-writable-by-others and UTF-8. Reject path traversal, symlinks, FIFOs, hardlinks, unsafe directories, oversized or mutated files.
- Git blob SHA-1 is calculated over the Git blob header and exact bytes; SHA-256 is recorded for the content. The Git branch/commit-to-blob association must be **independently checked** against the archived GitHub commit. This module does not verify commit ancestry, host identity, authorship, running RustWorld or scientific truth.
- A receipt HMAC only proves local consistency under an uncompromised private key. The source SHA, timestamp, command, input/output SHA and exit status are in the durable research job. No retry after uncertain execution or duplicate job ID.
- Source checkout is read-only; evidence DB is private (0700 parent, 0600 files). Run under a dedicated unprivileged UID. A same-UID attacker or malicious host is outside the guarantee.
- This is a **library capability, not a network endpoint**. A future broker must independently authenticate caller and source ID; no unrestricted HTTP/SSH shell or UI capability is provided. PAUSE_UI_WRITES and B1 PR #22 remain unchanged. A source receipt is not authorization for ChatGPT Send.

## Rolf handoff and next falsifiers

Rolf can inspect the [three original RustWorld source files](https://github.com/martintommerstigen/GTRCM/tree/RustWorld/source/Dokumenter) through GitHub now. C12 is an archived-code candidate identity collision, NOT current RustWorld Zero behavior; a real Rust test should compare node IDs 1 and 18446744073709551617. When Greg becomes available, first verify a real local checkout and exact blob bytes; only then run the read-only adapter under a dedicated UID. Compare its output with an independent GitHub blob fetch. Next inspect the archived RustWorld source/protocol.rs and RFP identity/parser code, then current RustWorld Zero source if authorized.

**Status:** source-read, implementation committed, CI verification pending until a run on this exact head completes. Greg remains blocked by explicit Desktop Commander monthly quota, with instruction not to retry or reconnect. No live existing-chat A→B→C wake.
