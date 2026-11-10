# B5/B2 — read-only receipt reconciliation after uncertain HTTP admission (2026-11-10)

**Ownership:** Ronja independent security branch, draft PR #8. This note follows Baton issue #3, PR #4, project-map B5/B2, forum #6, and GTRCM `METHOD.md` (not-NEI is not JA). The existing ChatGPT conversation A→B→C acceptance contract is unchanged.

## Gap and implementation

The one-shot HTTP client deliberately never retries after a timeout or unexpected response. Until this change, the documented operator procedure required ad hoc SQLite inspection, which could mistakenly promote an absent record into proof that nothing was received, or an unsigned envelope-only record into authenticated delivery.

`remote_security/receipt_audit.py` is a **local read-only reconciliation CLI**. It accepts a private SQLite database path, exact sender/message IDs and a private sender-key file. It opens an existing owner-only regular database in SQLite `mode=ro`, checks the two tables under one read transaction, verifies canonical envelope bytes, HMAC-SHA256, signed payload digest and receipt fingerprint, and returns one of:

- `present_authenticated_payload`: exact signed payload and local admission receipt agree; **NOT delivered or woken**.
- `present_envelope_only_unverified`: legacy envelope-only receipt exists, without independently verifiable payload.
- `absent_unknown`: no local receipt; **not evidence that the server did not receive a request**.
- `corrupt_untrusted`: contradictory, forged or altered local record.

Every result has `send_permitted=false`. The CLI neither sends nor authorizes a retry. It prints no payload, HMAC key, conversation transcript, or user identity. It does not create a missing database, follow symlinked database paths, or accept shared-readable files. The existing `remote_security.private_store` parent-path policy is reused.

Run on the machine holding the private receipt database, after explicit authorization:

```sh
python3 -m remote_security.receipt_audit \
  --database "$HOME/.local/state/baton-remote/receipts.sqlite" \
  --sender sender000 --message-id testmessage0001 \
  --sender-key-file "$HOME/.config/baton-remote/sender.key"
```

## Verification and boundaries

New `tests/test_receipt_audit.py` covers 14 isolated local cases: absent/unknown, valid admission without delivery, legacy unbound record, wrong key, altered payload/envelope/signature/fingerprint/state, orphan payload, unsafe permissions, missing database, symlink/traversal, and no database modification. Tests were executed locally in an isolated Python environment with a minimal compatible private-path helper; **this is not yet a full checkout integration test or Greg-live verification**. The branch's GitHub Actions `remote-envelope.yml` discovers `tests/test_*.py` and is the authoritative repository-level CI check after commit.

Limits: HMAC here authenticates a local record against the configured shared sender key, not an independent witness of remote delivery. A same-UID malicious process is outside the filesystem threat boundary; run the agent under a dedicated unprivileged UID. A database path race or hardware crash can still make absence ambiguous. Do not automatically retry, do not alter `PAUSE_UI_WRITES`, and do not interpret a signed transport receipt as an assistant turn.

**Fault-injection implemented:** `tests/test_http_uncertain_admission.py` uses a loopback HTTP handler that drops the connection after the gate has committed but before sending 202. The one-shot client must report `DeliveryUncertain`, the offline audit must find `present_authenticated_payload`, and a separately attempted duplicate must fail. A second injected failure before COMMIT must leave `absent_unknown` without permitting retry. This tests the observable commit/response gap without killing a live process; a real process-kill/restart experiment remains an independent next falsifier.

**Status:** B5 tested-simulated for the isolated 14-case audit; two additional HTTP fault-injection tests committed, repository CI pending check. Greg-live blocked; B1 existing-chat wake not tested. Do not mark B5/B2 done.
