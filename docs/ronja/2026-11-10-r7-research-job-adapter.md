# Ronja R7 — B5/B2 read-only research-job adapter (2026-11-10)

**Scope:** narrow, authorized research data-check adapter, not a general shell, independent physics experiment, external LLM, or existing-ChatGPT-conversation wake. No network listener or arbitrary executable. This is session-bound software work, not a persistent agent identity.

## Historical gate and difference

Read [Baton issue #3](https://github.com/martintommerstigen/Baton/issues/3), [PR #4](https://github.com/martintommerstigen/Baton/pull/4), B1 broker/UI boundary and [PR #20](https://github.com/martintommerstigen/Baton/pull/20), R5/R6 transport/receipt source, [forum #6](https://github.com/martintommerstigen/Baton/issues/6), R6 claim register and 278-tip inventory, GTRCM private C01–C06 ledger and main METHOD/NEGATIVE_RESULTS, plus RustWorld source overview. Five additional original GTRCM files were retrieved from previously uninspected branch tips; private source bodies are **not copied here**.

R6 indexed **278 branch-tip trees**, but only **14 tips / 18 original files** had content retrieved in that run (some excerpts). A fresh paginated REST listing on 2026-11-10 returned **280 branch names (100+100+80; page 4 empty)**. Relative to R6, two research refs were added and one audit ref changed SHA. This is 280 branch heads listed, NOT 280 histories read. The 278-tip artifact remains a dated snapshot. Historical non-tip commits, most branch contents, Greg/Mac sources and complete conversations remain unreviewed. No global historical priority claim.

**Already done:** R5/R6 Gate binds authenticated transport envelopes to payload bytes and durable admission, not to executed research checks. GTRCM source/clock/access negatives already separate records from independent physical witnesses. **Specific difference:** bounded fixed-command data checks, with durable one-shot reservation and signed source/run receipts. This is a software application, not a new GTRCM GEN result.

## Security and provenance contract

Exactly three builtins: sha256-echo, json-object-check, utf8-line-count. Exact request keys: project, job_id, command, input_sha256. Explicit project/command allowlist, SHA-256 checked before reservation, max 65,536 input bytes. No request path, argv, Python module, arbitrary command, network URL or external code. No project source tree is mounted or changed. Only an owner-only SQLite receipt DB is written.

Private 32–256-byte HMAC-SHA256 key from owner-owned regular file without following symlinks. Receipt includes project, job ID, command, policy SHA-256, on-disk adapter source SHA-256, exact input/output SHA-256, UTC timestamps, exit status and evidence class local_builtin_check_not_independent_measurement. The source hash is a pointer to on-disk bytes, **not** proof of loaded code identity. HMAC is shared-secret attestation, not independent third-party proof. Same-UID or key compromise defeats this trust boundary. Raw input is not stored; JSON validation reveals only field count, not keys or values.

Durable started_uncertain reservation precedes checking. Crash after reservation remains started_uncertain_no_retry across restart; duplicate (project,job_id) always fails. Read-only audit verifies HMAC, canonical receipt, policy and output digest. Not-found is not proof of nonexecution. No blind retry, UI write or A→B→C permission. Low-entropy input hashes can leak information; share receipts only with authorization and never commit raw private inputs or keys.

## Local installation (NOT executed on Greg)

Run from an authorized Baton checkout as a dedicated unprivileged service UID. Create an owner-only state directory and generate a private local key (never GitHub secrets):

    umask 077
    mkdir -p "$HOME/.local/state/baton-research"
    chmod 700 "$HOME/.local/state/baton-research"
    python3 -c 'import secrets,sys; open(sys.argv[1],"xb").write(secrets.token_bytes(32))' "$HOME/.local/state/baton-research/receipt.key"
    printf '{"sample":1}' | python3 -m remote_security.research_jobs \
      --database "$HOME/.local/state/baton-research/jobs.sqlite" \
      --receipt-key-file "$HOME/.local/state/baton-research/receipt.key" \
      --allow GTRCM:json-object-check --project GTRCM \
      --job-id check0001 --command json-object-check \
      --input-sha256 820a466daef9ca8e876a17e665f95e9ae4e6b407f8a01d51ad2d6bbc6e642b7b

The example hash is for exactly the shown input bytes with no newline; recompute for different bytes. To reconcile without execution, use the same command plus --audit (no stdin, command or input-sha needed). CLI exit 0 = valid check; 2 = completed invalid-data check with signed receipt; 3 = rejected/uncertain. Audit requires the original policy and key after rotation.

## Tests, coordination and remaining limits

[Negative tests](../../tests/test_research_jobs.py) cover forged input/output, policy bypass, path injection, duplicate JSON keys, invalid JSON, size, replay, six-way concurrency, crash after reservation, restart, tampered DB rows, key/policy rotation, symlink DB/key and unsafe permissions. [Socket-swap test](../../tests/test_remote_broker_socket_swap.py) forces real Linux client UID 1000 to pause after pathname verification of broker UID 65534, replaces the socket with a root-owned listener whose inode metadata is forged to the expected UID, then verifies SO_PEERCRED rejects the connected process before sending bytes. It requires isolated root/setpriv and is skipped in non-root hosted CI. This is NOT a test of B1's UI writer.

Next: independently install/test on Greg under dedicated UID when authorized access exists; separately design sandboxed external test executor with immutable argv/code pins, read-only mount, no network, CPU/memory/time limits and fail-closed sandbox detection. Do not extend this builtin into a generic subprocess endpoint. Integrate B1 only through reviewed peer-verified interface and preserve PAUSE_UI_WRITES/no-blind-retry. Require actual existing A/B/C conversation IDs and fresh assistant turns for any wake claim.

Status: tested-simulated for local data checks; tested-isolated Linux for real-UID socket swap; blocked for Greg-live; existing-chat A→B→C unverified. CI must be checked after push. B1-owned code, GTRCM private sources, Vanja/Eik branches and the project-map registry are unchanged.
