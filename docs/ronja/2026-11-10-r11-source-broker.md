# Baton Remote R11 — fixed-ID RustWorld source broker (B5/B2)

2026-11-10. **Implemented/tested offline; not installed on Greg.** This extends [R10 PR #26](https://github.com/martintommerstigen/Baton/pull/26) with a dedicated-UID Unix-socket RPC server. It does not change B1's browser/UI runner, PAUSE_UI_WRITES, Core, or the existing-chat A→B→C acceptance contract.

## Historical source and novelty gate

- [Issue #3](https://github.com/martintommerstigen/Baton/issues/3), [PR #4](https://github.com/martintommerstigen/Baton/pull/4): a transport receipt, SIWC or forum is not a verified existing ChatGPT conversation turn.
- [PR #20](https://github.com/martintommerstigen/Baton/pull/20) already implements the *client* SO_PEERCRED gate. Use its existing \`remote_security.broker_peer.query_verified_broker\` with the exact service UID. R11 implements the separate *server* fixed-source policy.
- [R9/R10 PR #23/#26](https://github.com/martintommerstigen/Baton/pull/26) already provides three pinned RustWorld blob IDs, SHA-1 Git blob comparison, SHA-256, HMAC/SQLite receipts and private restart-auditable evidence. R11 reuses these; it does not claim a new source-attestation algorithm.
- [B1 launcher PR #24](https://github.com/martintommerstigen/Baton/pull/24): keep the desktop launcher exclusively in the invoking human's directory, never broker-owned. No shared writable install paths.
- GTRCM [C01–C06](https://github.com/martintommerstigen/GTRCM/blob/audit/cross-branch-claim-ledger-2026-11-10/research/audit/2026-11-10_CROSS_BRANCH_CLAIM_LEDGER.md), [Kaja 18 Oct](https://github.com/martintommerstigen/GTRCM/blob/kaja/hva-er-ting-2026-10-18/research/kaja_hva_er_ting/README.md), [Roger R39](https://github.com/martintommerstigen/GTRCM/blob/research/roger-r38-r41-micro-for-whom-2026-11-03/experiments/roger_r39_observer_as_physical_actor_2026_11_03.py), [Rolf O/K/I](https://github.com/martintommerstigen/GTRCM/blob/research/rolf-operative-memory-rustworld-2026-11-10/research/rolf/2026-11-10_OPERATIVE_MEMORY_OBSERVATION_RUSTWORLD.md), [Eik C13](https://github.com/martintommerstigen/GTRCM/blob/integration/eik-rustworld-zero-desktop-2026-11-10/research/eik/corpus/2026-11-10_G2_G4_RUSTWORLD_DESKTOP_O_K_I_SOURCE_GATE.md), [RustWorld Zero](https://github.com/martintommerstigen/GTRCM/blob/architecture/rustworld-zero-2026-11-02/rustworld_zero/README.md): source observation O is neither a new influence channel K nor persistent individuation I.
- [Full paginated GTRCM inventory](2026-11-10-r11-gtrcm-branch-inventory-288.json): **288 branch names/head SHAs (100+100+88+0)**, 277 unchanged-SHA tree/date records reused from the earlier 278-entry inventory and 11 changed/new refs independently refreshed with commit dates and untruncated trees. on 2026-11-10. Six selected original documents from six refs read directly in this run; **0/288 complete branch histories**. Older/archived branches, Mac/Greg local files and most conversations remain unexamined. No global priority or physics novelty claim.

## Fixed RPC contract

Only two actions, \`capture\` and \`audit\`, with exact JSON keys \`version=1\`, \`action\`, \`source_id\`, \`job_id\`. The source ID must be one of R10's three operator-pinned IDs; the job ID must match \`[A-Za-z0-9_-]{8,64}\`. No caller-provided path, command, shell, URL, project, key or policy. Reply contains only state and SHA hashes, never source text or secret. The broker is single-threaded, AF_UNIX-only, backlog 4, 3-second request timeout, 4096-byte strict single-line JSON, rejects duplicate keys/extra fields/NaN. A failed/ambiguous operation is \`rejected_or_uncertain_no_retry\`; no automatic retry.

Linux \`SO_PEERCRED\` verifies the connected caller's UID **before reading request bytes**. Root and same-UID caller are refused. A malicious same-UID service process remains outside the threat model. The socket parent must be owned by the dedicated broker UID, group-traversable but not group-writable or world-accessible; socket mode 0660. A pre-existing socket (including after a crash) blocks startup, never silently unlinked. Normal shutdown removes only the inode bound by this process.

## Operator-only local setup — not executed on Greg

Create separate non-root broker and human/controller UIDs plus a shared reader group. Configure a service-owned, reader-group-owned socket directory such as \`/run/baton-source\` mode **0710**, with safe real ancestors; broker process primary GID must be the reader group. Create a broker-only state directory mode **0700**, a random receipt key file mode **0600** containing at least 32 bytes, private evidence directory mode **0700**, and a fixed checked-out RustWorld archive. Never put keys in GitHub, environment logs, .desktop files or CLI arguments. Start under the broker UID from the reviewed Baton checkout:

\`\`\`bash
python3 -m remote_security.source_broker \
  --socket /run/baton-source/read.sock \
  --allowed-uid <human_numeric_uid> \
  --database /home/baton-source/private/jobs.db \
  --receipt-key-file /home/baton-source/private/key.bin \
  --evidence-dir /home/baton-source/private/evidence \
  --source-root /path/to/checked/GTRCM/RustWorld
\`\`\`

The caller must use the R5/R10 \`query_verified_broker\` client with expected broker UID. Example request: \`{"version":1,"action":"capture","source_id":"rustworld-world","job_id":"capture001"}\`. Then \`audit\` the same source/job ID after restart to verify the saved evidence. Never repeat a capture with the same ID after a timeout; investigate the receipt/evidence first.

The paired `remote_security.source_broker_client.request_pinned_source` wrapper calls the existing `query_verified_broker` kernel peer gate and requires an **exact matching** source ID, job ID, success state and two lowercase SHA-256 digests. Stale, forged, extra-field and mismatched responses raise `BrokerUncertain` without fallback or retry. The response is a local byte-provenance record, never UI authorization.

## Evidence, boundaries, next falsifier

- Local isolated Linux tests: **10/10 non-root tests pass**, plus **1/1 actual kernel cross-UID test** under root test harness (the other UID-specific cases are skipped in the opposite environment). CI verification is separate from these local tests.
- Negative tests: forged caller UID, same/root UID, duplicate JSON keys, unauthorized source/command/path, symlink ancestor, world-accessible parent, stale socket/restart, backend uncertain, no TCP socket.
- No Greg install, no Mac/iPhone build, no source capture from Greg, no physics measurement, no A→B→C. \`PAUSE_UI_WRITES\` and no blind retry remain unchanged.
- Next: run with real distinct Greg UIDs after authorized access resumes; independently inspect Unix socket ownership, TCP listening sockets, exact pinned source bytes and durable restart audit. A source receipt is not a wake or O→K/I evidence.
