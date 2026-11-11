# Ronja R25 — B5/B2 observer lifetime syscall gate (2026-11-11)

**Classification:** implemented and isolated non-root Linux kernel tests; GitHub CI is independently checked. NOT Greg-live or an A→B→C wake. Ronja-owned branch stacked on R24 PR #56. B1 owns its observer runner and UI. This branch changes only Ronja-owned code, tests, workflow, and this note.

## Historical/source gate

- [Issue #3](https://github.com/martintommerstigen/Baton/issues/3), [PR #4](https://github.com/martintommerstigen/Baton/pull/4): existing-chat wake needs three unchanged conversation IDs and new assistant-turn IDs. Neither Unix socket, CI nor synthetic witness is that evidence.
- [B1 H22 PR #55](https://github.com/martintommerstigen/Baton/pull/55): separate write-capable CDP collector and snapshot-only observer. [B1 H23 PR #57](https://github.com/martintommerstigen/Baton/pull/57), [runner](https://github.com/martintommerstigen/Baton/blob/feature/b1-r24-observer-preflight-2026-11-11/run_b1_snapshot_observer.py): R24 rechecked before each snapshot/witness, but checks are point-in-time.
- [R23 per-frame credentials](https://github.com/martintommerstigen/Baton/blob/research/ronja-r23-frame-credentials-2026-11-11/remote_security/frame_credentials.py) and [R24 original](https://github.com/martintommerstigen/Baton/blob/research/ronja-r24-observer-boundary-2026-11-11/remote_security/observer_boundary.py) are prior work. R24 already rejects inherited connected sockets. H23 specifically asks whether an observer can receive a new connected CDP FD via SCM_RIGHTS after preflight.
- [GTRCM C01–C06 provisional ledger](https://github.com/martintommerstigen/GTRCM/blob/audit/cross-branch-claim-ledger-2026-11-10/research/audit/2026-11-10_CROSS_BRANCH_CLAIM_LEDGER.md), [Rolf O/K/I original](https://github.com/martintommerstigen/GTRCM/blob/research/rolf-operative-memory-rustworld-2026-11-10/research/rolf/2026-11-10_OPERATIVE_MEMORY_OBSERVATION_RUSTWORLD.md): source-access receipt (O) does not establish influence (K) or individuation (I).
- Two full selected original GTRCM bodies read: [Vega 29 Oct full-world gauge correction](https://github.com/martintommerstigen/GTRCM/blob/vega/embedded-clock-loss-rate-gauge-2026-10-28/research/vega/2026-10-29_full_world_endogenous_gauge_no_go.md) and [Svale 28 Oct two-tick witness](https://github.com/martintommerstigen/GTRCM/blob/svale/embedded-loss-witness-selection-2026-10-28/research/svale/2026-10-28_physical_witness_clock_joint_access.md). These concern physical calibration, not Linux syscall security; no new physics claim.

**Coverage:** GitHub REST pagination 2026-11-11 returned 312 distinct GTRCM branch names and 312 tip SHAs, pages 100+100+100+12. This is 312 indexed tips, not 312 inspected branch bodies. This run read two selected GTRCM original bodies plus Rolf and ledger, and relevant Baton originals; **0/312 complete branch histories**. Dates, themes, file lists and earliest ancestry for most branches remain uninspected. Greg, Mac, private conversation histories and 525 were not accessed. No corpus-wide novelty claim.

## Precise code delta

H23's repeated R24 preflight does not prevent future SCM_RIGHTS or pidfd_getfd. R25 applies a persistent Linux seccomp-BPF filter before B1's observer runner: deny recvmsg/recvmmsg, sendmsg/sendmmsg, pidfd_getfd, ptrace, process_vm_readv/process_vm_writev, io_uring_setup/io_uring_enter/io_uring_register, and socket(AF_INET/AF_INET6). It uses the system libseccomp2 via ctypes, no pip package or shell. PR #57 retains ownership of R24 preflight and pause checks. The filter is inherited by child processes and cannot be relaxed by unprivileged code. This is a known Linux mechanism applied to the observer, not a new general security theorem.

- [Implementation](../../remote_security/observer_lifetime_guard.py): install_observer_lifetime_guard() and fixed entry point: python3 -m remote_security.observer_lifetime_guard [B1 observer arguments]. No arbitrary command or external shell. B1's run_b1_snapshot_observer.py must be present in the integrated deployment; this branch does not copy or overwrite B1's file.
- [Kernel tests](../../tests/test_observer_lifetime_guard.py): non-root subprocesses confirm kernel denial of both TCP families and recvmsg/sendmsg, while AF_UNIX sendall/recv remains usable; inherited connected socket causes fail-closed refusal. Root is separately denied.
- [CI workflow](../../.github/workflows/ronja-r25-observer-lifetime.yml): branch Linux runner, non-root kernel tests, root rejection.
- Run only as a dedicated non-root observer UID after independently authorizing B1 H23 parameters. Never in the collector, broker or shared Python process. Restrictions are irreversible in the current process; terminate on any error.

## Negative result and limits

A point-in-time preflight cannot stop a future descriptor transfer. R25 denies the receiver's recvmsg/recvmmsg syscalls and pidfd_getfd path, rather than hoping another preflight runs in time. This removes those specified paths in the guarded process. AF_UNIX socket creation/connection remains allowed; a privileged or compromised host or undeclared AF_UNIX CDP endpoint is not ruled out. Ordinary recv() does not yield ancillary file descriptors. Other future code paths and kernel policy require separate audit. A collector could lie about DOM; no OS policy proves ChatGPT authorship.

**Do not deploy to Greg solely from these tests.** First combine R25 with B1 H23 in a version-pinned authorized tree, under distinct observer/collector/broker UIDs. Check libseccomp and R24 on Greg, deny browser-profile and undeclared CDP Unix access, test live CDP denial and authenticated snapshot success, remove one isolation rule deliberately and require denial. Preserve PAUSE_UI_WRITES and no blind retry. Actual A→B→C must be separately verified.

**Next falsifier:** Can the guarded observer still obtain an AF_INET-connected descriptor through a permitted syscall, or reach CDP through an undeclared AF_UNIX endpoint? If so, retain BLOCKED. No Desktop Commander, credential extraction, UI Send or external contact was used.


## Actual test receipts (post-implementation correction)

The first non-root suite passed (4/4), but the **first privileged cross-UID CI failed** because the GitHub checkout is not readable after changing to an unrelated UID. The test was corrected to preload the actual R24 module *before* dropping privileges; no policy bypass was added. A second local control used a test-only R24 stub for isolated prototyping and is **not** counted as an independent repository integration.

- [Exact-head GitHub Actions run 43019534431](https://github.com/martintommerstigen/Baton/actions/runs/43019534431) **SUCCESS** at commit eedc26e: six non-root tests PASS, one privileged-only test SKIP; the separate root runner's **one actual two-UID AF_UNIX test PASS**, plus root-observer rejection PASS. The server and client used real Linux UIDs 29111 and 29112, with synthetic response bytes; this is not Greg.
- The subsequent [cross-UID test change](../../tests/test_observer_lifetime_guard_cross_uid.py) injects an actual SCM_RIGHTS descriptor from the unconfined broker while the guarded observer uses the real broker_peer recv() path. It requires no extra FD remain in the observer. The kernel test was exercised in an isolated local Linux environment, but its GitHub exact-head CI must be checked separately.
- [Persistence negatives](../../tests/test_observer_lifetime_guard_persistence.py) confirm the kernel denies pidfd_getfd and preserves socket restrictions after exec, not merely before a simulated restart.

**Status boundaries:** syscall filter and synthetic AF_UNIX query = tested-simulated with real Linux kernel; integration into B1 H23 observer runner = implemented-unverified; Greg/CDP/525/live ChatGPT = blocked. A successful source snapshot is O, not K or I.
