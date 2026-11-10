# Ronja R8 — B5/B2 fixed-source Linux counter capture (2026-11-10)

## Historical gate and source coverage

The source gate precedes this implementation. Read the provisional [GTRCM C01–C06 ledger](https://github.com/martintommerstigen/GTRCM/blob/audit/cross-branch-claim-ledger-2026-11-10/research/audit/2026-11-10_CROSS_BRANCH_CLAIM_LEDGER.md), [Baton issue #3](https://github.com/martintommerstigen/Baton/issues/3), [PR #4](https://github.com/martintommerstigen/Baton/pull/4), [PR #20](https://github.com/martintommerstigen/Baton/pull/20), [PR #21](https://github.com/martintommerstigen/Baton/pull/21), the full latest [forum #6](https://github.com/martintommerstigen/Baton/issues/6), R7 research-job source/tests, GTRCM main negative results, Kaja C01 and Egil R76 original text.

Fresh GitHub REST pagination returned **282 branch names** (100+100+82, fourth page empty) in this run. This is NOT 282 content-read histories or a new SHA/date/tree snapshot; reuse the [R6 278-tip metadata inventory](2026-11-10-gtrcm-branch-inventory.json) only as its dated historical snapshot. Three additional previously uninspected branch-tip original files were fetched: [Hedda H8](https://github.com/martintommerstigen/GTRCM/blob/hedda/full-fysisk-utledningsrevisjon-2026-10-25/research/hedda/2026-10-26_h8_observatoren_inne_i_dynamikken.md) (blob `0765a187ba36b665c3fb6fa01a438bd08ae71239`), [Bodil boundaries](https://github.com/martintommerstigen/GTRCM/blob/bodil/boundaries-differences-2026-10-10/notes/ontology/2026-10-10_bodil_differences_boundaries_things.md) (blob `6f94ddd501a61fcde1c710e95f8becb30c1c77f7`), [RustWorld protocol](https://github.com/martintommerstigen/GTRCM/blob/RustWorld/source/protocol.rs) (blob `171b060f91d726f15479a6728993219225a6d1da`). Each is one file, not a complete branch review. No Greg/Mac source files or full prior conversations read in this run; Greg remote quota remains 0%.

## Prior art and precise delta — B5-RJ02

- **Already done:** [Egil R15c](https://github.com/martintommerstigen/Baton/issues/6#issuecomment-6775333905) previously captured genuine Greg `/proc/stat` under a time-ordered protocol; this is **not** the first GTRCM or Baton encounter with Linux kernel counters. R7 [research_jobs.py](../../remote_security/research_jobs.py) already executes fixed caller-byte checks with private HMAC/SQLite receipts, not independent nature measurement. Egil R76 already explains how access/sampling aliases physical histories; Kaja C01 already separates observation from persistent closure.
- **Changed assumption:** R7 checked only *caller-supplied* bytes. R8 fixes one authorized Linux source path (`/proc/stat`), reads its aggregate CPU line using `O_NOFOLLOW`, validates a bounded numeric grammar, binds the raw bytes to the existing durable R7 job receipt, and emits an additional domain-separated HMAC capture envelope. No arbitrary file, URL, shell, or project command.
- **Not a new physics result:** the source is a kernel-exposed system counter, not an independent calibrated physical experiment, GTRCM GEN prediction, ChatGPT wake, or attestation of the kernel's truth. A privileged host/mount-namespace attacker or same-UID key compromise remains outside the guarantee. HMAC and source hashes attest only local record consistency under the specified trust assumptions.
- **Next falsifier:** compare a real Greg capture against an independent host-level raw observation with a recorded host identity and calibrated clock, then test key compromise, procfs substitution and restart. No Greg test is claimed here.

## Contract with B1 PR #20/#21

The research job runs entirely outside the UI writer. It never calls `admit`, `begin_click`, Playwright, the browser, or a broker. A completed read-only receipt **cannot** authorize a B1 Send. The B1 source-turn text mutation after observation, raised in [forum #6](https://github.com/martintommerstigen/Baton/issues/6#issuecomment-6775734209), remains a separate unresolved UI observation-integrity problem. `PAUSE_UI_WRITES` and no-blind-retry are unchanged.

## One reproducible authorized job

On a Linux machine with a real `/proc/stat`, use a dedicated unprivileged account and owner-only state directory. Generate the private HMAC key locally; never store it in GitHub or in CI secrets. This command is an illustrative local invocation, **not executed on Greg**:

```python
from pathlib import Path
from remote_security.research_jobs import ResearchJobs
from remote_security.proc_stat_capture import capture_once, verify_capture
import json

state = Path.home() / ".local/state/baton-research"
state.mkdir(mode=0o700, parents=True, exist_ok=True)
key = (state / "receipt.key").read_bytes()  # provision privately with mode 0600
jobs = ResearchJobs(state / "jobs.sqlite", key, {"GTRCM": ["sha256-echo"]})
bundle = capture_once(jobs, "GTRCM", "cpu-20261110-01")
print(json.dumps(bundle, sort_keys=True))
print(verify_capture(jobs, bundle))
```

The bundle includes the exact raw aggregate CPU line (save it securely), source kind/path, raw SHA-256, adapter source SHA-256, capture-module source SHA-256, UTC observation time, receipt SHA-256 and a domain-separated HMAC. The nested durable job receipt contains command, project/job ID, input/output SHA-256, policy/source SHA-256, UTC start/end, exit status, evidence class and HMAC. To audit after restart, construct `ResearchJobs(..., audit_only=True)` and call `verify_capture` with the original bundle; do not run the same job ID again.

If the raw bundle is lost, the R7 durable receipt remains but does not reconstruct the original bytes or independently prove that `/proc/stat` was sampled. This is a deliberately conservative provenance limit.

## Status and ownership

Files owned by Ronja B5/B2: `remote_security/proc_stat_capture.py`, `tests/test_proc_stat_capture.py`, this document. No edits to B1 code, GTRCM/RustWorld sources, project-map/tasks.json, or UI pause state. Local Linux CI evidence must be checked against the exact code commit after push. Greg-live and existing-chat A→B→C remain **blocked/unverified**. The previous R7 job tests and B1 PR #20 remain distinct.
