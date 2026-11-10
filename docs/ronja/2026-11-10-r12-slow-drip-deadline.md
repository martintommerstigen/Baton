# Ronja R12 — B5/B2 bounded source RPC: slow-drip counterexample (2026-11-10)

Status: **implemented-unverified** until the new code/test commit passes hosted CI; **blocked** for Greg/Mac/iPhone. No UI write, shell, external contact, network listener, general filesystem RPC, or actual A→B→C. This is a software transport finding, not new GTRCM physics.

## Historical gate and coverage

- GTRCM [C01–C06 ledger](https://github.com/martintommerstigen/GTRCM/blob/audit/cross-branch-claim-ledger-2026-11-10/research/audit/2026-11-10_CROSS_BRANCH_CLAIM_LEDGER.md), Kaja C01, Egil R76, main NEGATIVE_RESULTS, [Rolf O/K/I](https://github.com/martintommerstigen/GTRCM/blob/research/rolf-operative-memory-rustworld-2026-11-10/research/rolf/2026-11-10_OPERATIVE_MEMORY_OBSERVATION_RUSTWORLD.md), RustWorld README, and original [Andreas G30](https://github.com/martintommerstigen/GTRCM/blob/research/andreas-g30-dependency-identifiability-interventions-2026-11-04/research/gaia/2026-11-04_ANDREAS_G30_DEPENDENCY_IDENTIFIABILITY_INTERVENTIONS.md), [Riss R17](https://github.com/martintommerstigen/GTRCM/blob/research/riss-r17-lodd-contact-meter-2026-11-07/research/riss/2026-11-07_RISS_R17_LODD_KONTAKT_ELLER_MAALER.md), and [Knut R1](https://github.com/martintommerstigen/GTRCM/blob/research/knut-r3-relative-change-without-persistence-2026-11-06/research/knut/2026-11-06_KNUT_R1_HISTORIE_LUKNING_KRYSSKONTAKT_OBJEKTIVITET.md) were read from their exact refs; 9 original GTRCM text files / 9 refs this run, **0 complete branch histories**. The Knut R1 text on the R3 branch is not evidence R3 was completely read.
- Fresh GitHub branch search pages returned **100 + 100 + 89 + 0 = 289 GTRCM branch names**, not 289 read contents. Earlier [R11 inventory of 288](https://github.com/martintommerstigen/Baton/blob/research/ronja-r11-source-broker-2026-11-10/docs/ronja/2026-11-10-r11-gtrcm-branch-inventory-288.json) remains an older SHA/tree snapshot; this run did not refresh all 289 commit SHA/tree records. Existing conversations were only available as supplied context, not exhaustively fetched. Greg/Mac source files were not accessible; no Desktop Commander used.
- Baton [issue #3](https://github.com/martintommerstigen/Baton/issues/3), [PR #4](https://github.com/martintommerstigen/Baton/pull/4), [PR #20](https://github.com/martintommerstigen/Baton/pull/20), [R11 PR #28](https://github.com/martintommerstigen/Baton/pull/28), [B1 PR #29](https://github.com/martintommerstigen/Baton/pull/29), [forum #6](https://github.com/martintommerstigen/Baton/issues/6) and the separate launcher integration branch were consulted. No B1 or launcher files modified.

## Earlier result versus precise delta

R11 already has a fixed source-ID, dedicated-UID AF_UNIX broker with kernel SO_PEERCRED, strict JSON frame, bounded frame length, a **3-second timeout per recv**, and no blind retry. R5 broker_peer client likewise has a per-recv timeout and verified peer UID. The earlier security tests cover replay, invalid frames, fake sender, path traversal, restart and uncertainty; the present two source files and their tests did not bound **total elapsed time** while a peer continued sending bytes.

**Falsifiable R12 difference:** a permitted UID can keep the *single-threaded* broker occupied by sending one byte just before each per-recv timeout. Likewise a connected broker can keep the client waiting by trickling reply bytes. A fixed frame-size limit does not bound time when the peer sends slowly. This is a conventional slowloris/resource-exhaustion class, not a novel theorem. It is a denial-of-service availability boundary, not proof of a forged identity or UI wake.

**Change:** use monotonic absolute deadlines for the entire server request frame and entire client reply frame, without changing allowlisted source IDs, broker identity checks, persistence, UI pause, or retry policy. Timeouts remain uncertain/no-retry, even when backend outcome is unknown. No new permissions or socket/network exposure.

**New negative tests:** `tests/test_source_broker.py::BrokerTests.test_authorized_slow_trickle_cannot_hold_single_threaded_broker` and `tests/test_remote_broker_peer.py::BrokerPeerTests.test_slow_trickle_reply_has_absolute_deadline`. Both deliberately keep the connection active while sending partial bytes, then require bounded termination without invoking the source capture backend or treating partial reply as success. The previous per-recv implementation would exceed the test deadline. CI and Greg verification must be reported separately.

## GTRCM provenance / claim entry B5-RJ04

- **Claim:** A bounded per-call `recv` timeout plus bounded message size does not imply bounded total processing time against an authorized slow sender.
- **Assumptions:** streaming socket; each partial read arrives within the per-call timeout; server processes one connection at a time.
- **Counterexample:** one byte every 40–50 ms, no complete frame, for longer than a 200 ms absolute deadline.
- **Earlier source:** R11 `remote_security/source_broker.py`, R5/R11 `remote_security/broker_peer.py`; no monotonic frame deadline in the inspected original. Classification **sharpened security counterexample / implementation**, not new GTRCM mathematics or independent measurement.
- **Falsifier:** show that the original per-recv-only loop terminates within a fixed elapsed budget under arbitrarily long valid partial-byte arrivals. It does not under the stated model.
- **Scientific boundary:** SHA/HMAC/local receipt is an O observation of selected bytes, not K intervention, I individuation, calibrated physical measurement, host identity or existing-chat wake. Rolf O/K/I and Egil contact limitations remain applicable.

## Release and next test

CI on Linux is a synthetic/local socket test, not Greg. Before Greg deployment: install dedicated broker UID and different caller UID, verify actual AF_UNIX permissions and no TCP listener, perform one real pinned RustWorld source capture/audit across restart, inspect `ss -ltn`, and retain source SHA, raw capture, UTC, exit status and evidence SHA. Never invoke UI Send or infer A→B→C from this result. Greg access is deliberately deferred until authorized free access exists. 525 Xcode/iPhone signing and actual launch remain unverified.
