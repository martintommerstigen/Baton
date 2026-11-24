# Ronja R18 — B5/B2 read-only local observation manifest (2026-11-11)

**Classification:** implemented and locally tested software application, **not** a new GTRCM physics result, Greg installation, host attestation, or ChatGPT A→B→C. Stacked on [R17 PR #40](https://github.com/martintommerstigen/Baton/pull/40). Own files: `remote_security/host_manifest.py`, `tests/test_host_manifest.py`, this note. No B1 code or UI write policy changed.

## Historical source gate and measured coverage

- [Baton issue #3](https://github.com/martintommerstigen/Baton/issues/3), [PR #4](https://github.com/martintommerstigen/Baton/pull/4), [B1 H15 PR #41](https://github.com/martintommerstigen/Baton/pull/41): a socket receipt, a browser lock, and a GitHub comment do not establish a new assistant turn in an existing conversation. `PAUSE_UI_WRITES` and no-blind-retry remain unchanged.
- [R17 source probe](https://github.com/martintommerstigen/Baton/blob/research/ronja-r17-source-probe-2026-11-11/remote_security/source_broker_probe.py) already distinguishes socket metadata from connected Linux `SO_PEERCRED`. R18 **reuses** it, adding a bounded, non-secret observation manifest; not a new authentication primitive.
- [Baton desktop integration launcher](https://github.com/martintommerstigen/Baton/blob/integration/baton-desktop-launcher-2026-11-10/desktop/install_baton_launcher.py) uses an installable .desktop file but has insufficient parent-symlink and preexisting-file protections. R18 does not modify or certify that installer; it is a separate read-only diagnostics route, not a release launcher.
- [Rolf O/K/I](https://github.com/martintommerstigen/GTRCM/blob/research/rolf-operative-memory-rustworld-2026-11-10/research/rolf/2026-11-10_OPERATIVE_MEMORY_OBSERVATION_RUSTWORLD.md), [Tiril Katteluka 12 Oct](https://github.com/martintommerstigen/GTRCM/blob/tiril/rustworld-care-and-generations-2026-10-12/prototypes/525-minimal-brain-senses-v1/experiments/KATTELUKA_FEEDBACK_VS_REPLAY_2026-10-12.md), [Kaja 17 Oct](https://github.com/martintommerstigen/GTRCM/blob/kaja/virksom-historie-2026-10-17/experiments/kaja_virksom_historie/README.md): observing a trace or replay is not evidence of a particular active influence channel. [Andreas G29](https://github.com/martintommerstigen/GTRCM/blob/integration/andreas-g29-channel-dependency-rustworld-2026-11-04/research/gaia/2026-11-04_ANDREAS_G29_RUSTWORLD_CHANNEL_DEPENDENCY.md): multiple receipts may share a single upstream source.
- [Riss R20 original 7 Nov](https://github.com/martintommerstigen/GTRCM/blob/research/riss-r20-multichat-learning-2026-11-07/research/riss/2026-11-07_RISS_R20_FLERE_CHATTER_LAERER_HVERANDRE.md): actual existing-chat sends were reported and the shared UI lock had to be released before reply wait; no evidence of current wake follows from this manifest.
- [Archived RustWorld world.rs](https://github.com/martintommerstigen/GTRCM/blob/RustWorld/source/Dokumenter/kindergarden/src/world.rs), blob `8e579d97456641e626dc56bf34505713aab46e72`: archived source, **not** Greg process state. [Provisional C01–C06 claim ledger](https://github.com/martintommerstigen/GTRCM/blob/audit/cross-branch-claim-ledger-2026-11-10/research/audit/2026-11-10_CROSS_BRANCH_CLAIM_LEDGER.md) checked before change.
- Full paginated GitHub branch API returned **298 GTRCM tip names/SHAs** (100+100+98+0), on 2026-11-11. [R18 machine inventory](2026-11-11-r18-gtrcm-branch-inventory-298.json) reuses dated tree/path metadata for 296 unchanged SHAs and refreshes both changed/new tips. **Eight exact original GTRCM file bodies read** (Tiril, Riss, Kaja, RustWorld, Andreas, Rolf, Eik C28, Vanja R36), plus the provisional claim ledger, Baton sources and forum. **0 complete GTRCM branch histories** read. Metadata indexing is not a full content audit; Greg/Mac/other private history not read. No claim of novelty relative to all branches.

## B5-RJ10: fail-closed local provenance *observation*, not attestation

**Falsifiable question:** Can B1/Rolf/Eik receive an operator-generated, non-secret *local* observation containing (a) service UID contact status, (b) socket inode snapshot, (c) source-file hashes, and (d) pause-marker existence without reading the marker, running jobs, touching UI, or interpreting absence as authorization?

Implementation: `remote_security/host_manifest.py`. It calls the preexisting `source_broker_probe.probe` exactly once. Default mode does **not** connect; opt-in `--connect-once` performs one AF_UNIX connection with zero application request bytes. A second post-probe pathname snapshot reports socket device/inode/owner/mode, explicitly **not atomic with the kernel peer check**. Source-file SHA256 hashes are bounded reads through no-follow, nonblocking file descriptors with type, hardlink and mutation checks. These are hashes of **on-disk files at observation time**, not runtime binary attestation or proof of installed commit. No paths, secrets, marker contents, tokens or raw source bytes are included in JSON.

The caller supplies the **exact** pause path. A present regular single-link marker reports `present_at_checked_path`; an absent marker reports `absent_at_checked_path_not_authorization`; missing path input reports `not_checked`. Symlink ancestors, symlink/hardlink marker, FIFO, mutable ancestors, malformed paths, replaced socket and uncertain peer fail closed. **Neither absence nor presence is proof of the effective UI pause state**: other policy sources and TOCTOU remain possible. The manifest has explicit `pause_authorization: never_inferred`, `ui_write: not_attempted`, `greg_live: not_established`, and `existing_chat_wake: not_established`.

Example **only after a separately authorized service installation**, with operator-confirmed values (not guessed):

```bash
python3 -m remote_security.host_manifest \
  --socket /absolute/service-owned/socketdir/source.sock \
  --service-uid 21001 \
  --pause-file /absolute/verified/transport/PAUSE_UI_WRITES

# Explicit local kernel contact; still not a source job or ChatGPT wake
python3 -m remote_security.host_manifest \
  --socket /absolute/service-owned/socketdir/source.sock \
  --service-uid 21001 --connect-once
```

**Negative controls:** eleven deterministic tests: default no-connect/no-authorization; present/absent pause without content; opt-in exactly one contact; no retry after uncertainty; symlink/hardlink marker; symlink parent/traversal; FIFO/mutable parent; symlink/hardlink source file; inode snapshot/replacement; fault-injected source pathname replacement during read; invalid connect flag. Locally run in isolated Python with stubbed broker modules: **11/11 PASS**. Source file SHA matches local tested file `10adad6bfe4efa84d276f53aed956d91137e8651`. Full Baton integration and trusted GitHub CI must be checked independently. No Greg access, no DC use.

**Next falsifier:** can an authorized, independent Greg-side service operator generate this manifest with confirmed UID and pause path, and can a second channel check that the file SHA corresponds to the *running* binary rather than a replaceable source file? An HMAC from the same process would still be a self-report, not independent host attestation. No actual RustWorld/525 launch or iPhone signing claim follows.
