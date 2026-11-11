# Ronja R17 — B5/B2 read-only source broker probe (2026-11-11)

**Classification:** software security/observability application; **not** new GTRCM physics. Branch `research/ronja-r17-source-probe-2026-11-11`, stacked on [R16 PR #38](https://github.com/martintommerstigen/Baton/pull/38). No B1 file ownership, no Greg/Mac access, no DC quota, no UI writes, no automatic retry, no external contacts.

## Source and historical gate

- [Baton issue #3](https://github.com/martintommerstigen/Baton/issues/3), [PR #4](https://github.com/martintommerstigen/Baton/pull/4), [B1 H13 PR #37](https://github.com/martintommerstigen/Baton/pull/37): a verified existing-chat wake needs actual A/B/C conversation and turn IDs, not local socket state. `PAUSE_UI_WRITES` remains unchanged.
- [Baton R16 source broker](https://github.com/martintommerstigen/Baton/blob/research/ronja-r16-endpoint-inode-2026-11-11/remote_security/source_broker.py) and [broker peer](https://github.com/martintommerstigen/Baton/blob/research/ronja-r16-endpoint-inode-2026-11-11/remote_security/broker_peer.py): previously implemented SO_PEERCRED, pinned directory/socket inode, no-retry. R17 **reuses** these checks; no new cryptographic claim.
- [Rolf O/K/I original](https://github.com/martintommerstigen/GTRCM/blob/research/rolf-operative-memory-rustworld-2026-11-10/research/rolf/2026-11-10_OPERATIVE_MEMORY_OBSERVATION_RUSTWORLD.md): observing an endpoint (O) does not grant influence (K) or operative individuation (I). A connection is a local contact, not a nature measurement.
- [Kaja cryptic memory, 18 Oct](https://github.com/martintommerstigen/GTRCM/blob/kaja/kryptisk-hukommelse-og-skjult-virkning-2026-10-18/research/kaja_kryptisk_minne/README.md): a future report need not reconstruct the source state. [Andreas G29](https://github.com/martintommerstigen/GTRCM/blob/integration/andreas-g29-channel-dependency-rustworld-2026-11-04/research/gaia/2026-11-04_ANDREAS_G29_RUSTWORLD_CHANNEL_DEPENDENCY.md): two observed channels do not imply independent upstream witnesses.
- [Eik C24](https://github.com/martintommerstigen/GTRCM/blob/integration/eik-rustworld-zero-desktop-2026-11-10/research/eik/corpus/2026-11-11_G2_G4_C24_COUNT_MATCHING_CONTENT_FALSIFIER.md): even a matching count may coexist with forged source content. [RustWorld world.rs](https://github.com/martintommerstigen/GTRCM/blob/RustWorld/source/Dokumenter/kindergarden/src/world.rs) is archived source, not Greg live state. [GTRCM main negative results](https://github.com/martintommerstigen/GTRCM/blob/main/NEGATIVE_RESULTS.md) prevents source reports from being elevated into physical GEN.
- [Provisional C01–C06 ledger](https://github.com/martintommerstigen/GTRCM/blob/audit/cross-branch-claim-ledger-2026-11-10/research/audit/2026-11-10_CROSS_BRANCH_CLAIM_LEDGER.md) checked before this software change. No physical claim proposed.
- [R17 paginated inventory](2026-11-11-r17-gtrcm-branch-inventory-297.json): 100+100+97+0 = **297** branch names and tip SHAs. 292 unchanged tip records reuse R16's indexed metadata; five changed/new refs had commit dates and trees refreshed. **7 original file bodies from 7 branch refs read in this run; 0 complete branch histories read.** Older and private chat corpus, Greg/Mac remain unreviewed. Metadata indexing is not source reading.

## B5-RJ09 — distinguish endpoint observation from authorized source capture

**Falsifiable question:** Can Eik/Rolf check whether a dedicated-UID local AF_UNIX source broker endpoint exists, and optionally verify the connected kernel UID, **without** sending a source capture/audit request or silently authorizing wake?

**Implementation:** [source_broker_probe.py](../../remote_security/source_broker_probe.py) offers two deliberately distinct observations:

1. Default metadata-only: strict canonical pathname and ancestor checks, expected owner UID, socket type and mode 0660. **No connect**; result `endpoint_metadata_only` is not proof of a live process.
2. Explicit `--connect-once`: one AF_UNIX connect, SO_PEERCRED UID check, pathname/endpoint recheck, **zero application request bytes**. Result `kernel_peer_uid_verified_no_request` proves only a matching local Linux peer UID at that contact. It may be noticed by the broker and therefore is **not a noninteracting measurement**. It is not a service binary attestation, source SHA, remote machine attestation, TCP exposure scan, ChatGPT wake or physical source calibration.

Root, same-UID, setuid, unknown UID, unsafe path, symlink ancestors, non-socket, world-writable endpoint and uncertain contact fail closed. No secret/key is loaded or printed. Exit 3 for rejection/uncertainty. No automatic retry.

**Offline use after an operator actually installs the dedicated service** (the socket path and UID are deployment-specific, not guessed from Greg):

```bash
python3 -m remote_security.source_broker_probe --socket /absolute/private/service/source.sock --service-uid 21001
python3 -m remote_security.source_broker_probe --socket /absolute/private/service/source.sock --service-uid 21001 --connect-once
```

The second command is **opt-in** because the connection is a real local influence/contact. Neither command reads source bytes or sends a research job. This is not a launcher for RustWorld/525.

**Negative evidence:** [7 local non-root cases](../../tests/test_source_broker_probe.py) cover forged UID, same UID, symlinked socket and parent, world-writable socket, missing endpoint, invalid timeout/flags. [Trusted Linux three-UID regression](../../tests/test_source_broker_probe_cross_uid.py) runs service 21001 and caller 21003 and checks zero backend callbacks in the **actual SourceBroker**, rather than a synthetic response. A second root-only negative fixture forges the socket inode owner to the service UID while the actual listener remains root; the connected kernel UID must still be rejected, with zero bytes sent. A third root-only fixture leaves a correctly owned stale AF_UNIX inode with **no listener**: metadata-only must not be promoted to a live-service claim, and opt-in connection fails uncertain. Root is used only by the CI test harness to fork disposable unprivileged identities, never by the production service.

**Test boundary:** Local isolated Linux testing is `tested-simulated` for fixture endpoints. Trusted GitHub CI is a real Linux UID/kernel test but still **not Greg-live**. The final code/test head must have a successful trusted-push CI run and decoded job logs before a CI pass is claimed; the actual Greg installation remains unverified. A successful metadata probe cannot establish the presence of a RustWorld binary, valid source capture, or A→B→C.

## Next falsifier

After authorized installation, compare metadata-only (O) and opt-in connected peer (local contact), then separately perform a pinned source capture, restart and audit with source SHA and evidence SHA. Check that a wrong UID, endpoint replacement, and a capture request during `PAUSE_UI_WRITES` do not cause a UI action. For independent physical measurement, add a separately controlled source-side event recorder; do not treat two receipts from one service UID as independent witnesses.
