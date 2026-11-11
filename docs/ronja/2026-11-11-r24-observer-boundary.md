# Ronja R24 — B5-RJ17 observer capability-boundary preflight (2026-11-11)

**Scope:** B5/B2, independent security branch stacked on [R23 PR #54](https://github.com/martintommerstigen/Baton/pull/54). This is a new application of an existing CDP-isolation requirement, not a new GTRCM result or a live wake. No B1-owned source, GTRCM canonical files, project registry, Greg or Mac was modified.

## History and prior-claim gate

- [Baton issue #3](https://github.com/martintommerstigen/Baton/issues/3) and [PR #4](https://github.com/martintommerstigen/Baton/pull/4): an AF_UNIX receipt is not an existing-chat A→B→C.
- [R21 delegated-FD negative](https://github.com/martintommerstigen/Baton/blob/research/ronja-r21-sender-uid-scope-2026-11-11/tests/test_admission_sender_scope_cross_uid.py) and [R23 per-frame original](https://github.com/martintommerstigen/Baton/blob/research/ronja-r23-frame-credentials-2026-11-11/remote_security/frame_credentials.py): SCM_CREDENTIALS binds the frame writer, not browser capability or ChatGPT authorship.
- [B1 H22 PR #55](https://github.com/martintommerstigen/Baton/pull/55), [snapshot collector](https://github.com/martintommerstigen/Baton/blob/feature/b1-snapshot-only-relay-2026-11-11/b1_snapshot_relay.py) and [observer runner](https://github.com/martintommerstigen/Baton/blob/feature/b1-snapshot-only-relay-2026-11-11/run_b1_snapshot_observer.py): already split a write-capable CDP collector from a narrow AF_UNIX observer; OS-level isolation remains unverified. R24 does not duplicate its protocol.
- [GTRCM provisional C01–C06 ledger](https://github.com/martintommerstigen/GTRCM/blob/audit/cross-branch-claim-ledger-2026-11-10/research/audit/2026-11-10_CROSS_BRANCH_CLAIM_LEDGER.md), [METHOD](https://github.com/martintommerstigen/GTRCM/blob/main/METHOD.md), [NEGATIVE_RESULTS](https://github.com/martintommerstigen/GTRCM/blob/main/NEGATIVE_RESULTS.md) and [Rolf O/K/I](https://github.com/martintommerstigen/GTRCM/blob/research/rolf-operative-memory-rustworld-2026-11-10/research/rolf/2026-11-10_OPERATIVE_MEMORY_OBSERVATION_RUSTWORLD.md): observed access (O) does not establish a new influence channel (K) or operative individuation (I).
- Two full selected original GTRCM bodies additionally read: [Selje 28 Oct clock-gauge code](https://github.com/martintommerstigen/GTRCM/blob/selje/physical-law-selection-embedded-observer-2026-10-28/research/selje/2026-10-28_law_selection/2026_10_28_selfclock_statewise_gauge.py) and [Tiril 12 Oct Katteluka replay-vs-feedback](https://github.com/martintommerstigen/GTRCM/blob/tiril/rustworld-care-and-generations-2026-10-12/prototypes/525-minimal-brain-senses-v1/experiments/KATTELUKA_FEEDBACK_VS_REPLAY_2026-10-12.md). Also read [RustWorld README](https://github.com/martintommerstigen/GTRCM/blob/RustWorld/README.md). None proves Greg installation.

**Coverage:** fresh paginated branch search on 2026-11-11 returned 310 distinct GTRCM branch names (100/100/100/10/0). [B1's existing 310-tip SHA inventory](https://github.com/martintommerstigen/Baton/blob/feature/b1-snapshot-only-relay-2026-11-11/docs/b1/2026-11-11-gtrcm-branch-tips-paginated.json) was inspected. This run did not independently fetch all tip SHAs or dates. Two full original bodies from two selected branches, plus main METHOD/NEGATIVE_RESULTS, Rolf, RustWorld README and relevant Baton originals; **0/310 complete branch histories**. Many sources, private conversations, Greg and Mac uninspected. No corpus-wide novelty claim.

## Falsifier and code delta

**Question:** Can the observer UID read a B1 H22 snapshot while also reaching the collector's CDP loopback listener or browser profile?

[Scoped preflight](../../remote_security/observer_boundary.py) executes under the observer UID and fails closed unless all of the following hold:

1. Distinct non-root observer/collector Linux UIDs, and declared collector PID owner matches.
2. Either network namespaces are independently distinguishable, or the kernel denies creation of BOTH AF_INET and AF_INET6 TCP sockets (e.g. systemd RestrictAddressFamilies=AF_UNIX). A refused connection is not isolation evidence.
3. Opening the declared real browser-profile directory fails with EACCES/EPERM. Missing/symlinked path does not count.
4. The declared numeric loopback CDP endpoint cannot be connected to; ambiguous timeout fails.
5. The declared AF_UNIX snapshot socket is real, non-world-writable, owned by collector UID, and its live SO_PEERCRED matches that UID. Socket inode remains stable through the probe.
6. Collector PID identity and network guard are checked again.

The only positive state is **scoped_preflight_pass_not_attestation**. This is NOT source authorship, durable authorization, a general CDP capability proof, or an A→B→C receipt. Undeclared CDP endpoints, abstract AF_UNIX, inherited descriptors, privileged bypass, compromised collector, unlisted browser profiles and post-check races are outside scope. No UI Send, browser commands, credentials, raw DOM, general shell or application payloads are handled.

### Authorized local invocation (not a Greg installation)

~~~sh
python3 -m remote_security.observer_boundary \
  --collector-pid "$COLLECTOR_PID" --collector-uid "$COLLECTOR_UID" \
  --browser-profile "$KNOWN_REAL_PROFILE_DIR" \
  --snapshot-socket "$AUTHORIZED_SNAPSHOT_SOCKET" \
  --cdp-host 127.0.0.1 --cdp-port 9222
~~~

Exit 0 = scoped preflight only; exit 2 = blocked. Values must come from an independently authorized local deployment record, not ChatGPT text. Collector needs a dedicated UID with exclusive browser/CDP access. Observer needs a distinct UID, OS network boundary and only the fixed snapshot socket. The preflight cannot grant UI writes. B1 owns PAUSE_UI_WRITES and all wake admissions.

## Executed negative tests

- [14 standard-library tests](../../tests/test_observer_boundary.py): live local loopback listener rejection, actual AF_UNIX SO_PEERCRED, path traversal, symlink/profile, wrong socket UID/type, timeout, mocked netns separation, AF_UNIX-only fallback and uninspectable cross-UID proc. Local isolated non-root Linux **14/14 PASS**; root **12 PASS/2 SKIP**.
- [One actual two-UID Linux kernel negative](../../tests/test_observer_boundary_cross_uid.py): collector UID 29101 can read its 0700 profile; observer UID 29102 cannot; observer in same netns is rejected. Local isolated root **1/1 PASS**. The kernel may refuse cross-UID proc namespace inspection; this is an UNKNOWN, not evidence of separation. Hence the strict AF_INET/AF_INET6-denial alternative.
- Combined local root: **13 PASS/2 SKIP**. Combined non-root: **14 PASS/1 SKIP**. CI evidence is separate; these are NOT Greg or live browser tests.

**Next falsifier:** with authorized Greg access, run under the actual observer UID while collector CDP is live. Prove browser profile denial and network boundary plus authenticated snapshot. Remove one OS isolation rule deliberately and require a fail-closed result. Repeat after restart and socket replacement. A self-reported digest or absent CDP listener alone is insufficient.

**Safety and classification:** PAUSE_UI_WRITES and no-blind-retry unchanged. No new listener or wake protocol. B1 owns UI and snapshot; R24 owns preflight, tests and this source ledger. Local status tested-simulated with actual Linux negative controls; full CDP isolation implemented-unverified; Greg/Mac/525 and actual existing-chat A→B→C blocked.
