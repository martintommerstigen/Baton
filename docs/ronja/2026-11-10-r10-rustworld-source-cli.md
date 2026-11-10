# Ronja R10 — B5/B2/R9 pinned RustWorld source probe (2026-11-10)

**Status:** offline code, pending CI and Greg deployment. No UI write, shell, SSH, HTTP listener, Core/Skin modification or ChatGPT wake. B1 owns the separate launcher in PR #24; R10 does not copy it.

## Historical gate and precise delta

Read [GTRCM C01–C06 ledger](https://github.com/martintommerstigen/GTRCM/blob/audit/cross-branch-claim-ledger-2026-11-10/research/audit/2026-11-10_CROSS_BRANCH_CLAIM_LEDGER.md), [Rolf O/K/I](https://github.com/martintommerstigen/GTRCM/blob/research/rolf-operative-memory-rustworld-2026-11-10/research/rolf/2026-11-10_OPERATIVE_MEMORY_OBSERVATION_RUSTWORLD.md), GTRCM main NEGATIVE_RESULTS, RustWorld README, Baton issue #3, PR #4/#20/#23/#24 and latest forum #6. Fresh paginated GTRCM API returned **285 branch names/head SHAs (100+100+85+0)**, not 285 content-read histories. This run read four GTRCM research documents from four refs and several original Baton source/test files; **zero complete GTRCM histories**. Greg/Mac source not inspected; no claim of complete novelty.

Prior work: R7 ResearchJobs already implements one-shot HMAC/SQLite receipts; R8 capture_bundle_store already implements exclusive private raw capture artifacts; R9 pinned_source already checks source ID, Git blob and safe dirfd walk. **R10 is a narrower product application, not new physics or new cryptography:** one fixed CLI for R9's three source IDs, durable one-shot private evidence file, read-only restart audit. Rolf O/K/I: this is increased source **observability O**, not proof of new channel K, individuation I, Git commit ancestry, host identity or physical measurement.

## Linux installation (instructions only; NOT run on Greg)

Use a dedicated non-root UID, trusted Baton R10 checkout, trusted archived GTRCM RustWorld checkout at claimed commit `94bed1f667179c6b9501a10ab34d2cca883f8760`. Verify the checkout's commit/tree independently; R10 only pins blob bytes. Evidence directory must be owned by agent, mode 0700; key 0600. No GitHub secrets.

```bash
umask 077
install -d -m 700 "$HOME/.local/state/baton-rustworld"
python3 -c 'import os,secrets; p=os.path.expanduser("~/.local/state/baton-rustworld/receipt.key"); fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600); os.write(fd,secrets.token_bytes(32)); os.fsync(fd); os.close(fd)'
```

From the trusted Baton repository root, one explicitly authorized job:

```bash
python3 -m remote_security.pinned_source_cli capture \
 --database "$HOME/.local/state/baton-rustworld/jobs.db" \
 --receipt-key-file "$HOME/.local/state/baton-rustworld/receipt.key" \
 --evidence "$HOME/.local/state/baton-rustworld/network-0001.json" \
 --source-root "/ABSOLUTE/PATH/TO/RUSTWORLD-ARCHIVE" \
 --source-id rustworld-network --job-id network0001
```

After restart, audit without reading source or running another job:

```bash
python3 -m remote_security.pinned_source_cli audit \
 --database "$HOME/.local/state/baton-rustworld/jobs.db" \
 --receipt-key-file "$HOME/.local/state/baton-rustworld/receipt.key" \
 --evidence "$HOME/.local/state/baton-rustworld/network-0001.json" \
 --source-id rustworld-network
```

Other allowlisted IDs: `rustworld-world`, `rustworld-node`. Output contains hashes and classification, **never source text, key or private paths**. A successful local HMAC receipt is not a host or scientific attestation.

## Falsifiers and remaining boundaries

Negative tests cover replay/duplicate job, changed source/policy, forged evidence, symlink/hardlink/FIFO, traversal, unsafe parent, interrupted fsync, root invocation, restart verification. The R9 suite additionally covers source symlink parents, mutation, non-UTF8 and oversize. An interrupted save may leave a partial artifact and an already-completed DB job; **never blind-retry that ID**. No network listener is exposed. A malicious same-UID process and dishonest host are outside the guarantee. `PAUSE_UI_WRITES` remains untouched.

**Greg:** no Desktop Commander use (monthly quota exhausted until at least 12 November); no install, RustWorld process, source capture, RFP smoke test or iPhone build claimed. **525:** archived Xcode projects exist under GTRCM RustWorld, but Mac/signing/iPhone not available for actual build. **B1:** PR #24's CLI-help icon is not a working RustWorld application; real GUI/525 release remains unverified.

Next: independent Git tree-to-blob check, authorized Greg dedicated-UID capture/audit with raw evidence and machine provenance, then a separate authenticated per-source-ID broker using B5 SO_PEERCRED. Do not grant arbitrary paths, shell or UI write.