# B5/B2 — Ronja R5: endpoint authentication before disclosure (2026-11-10)

Source: incremental branch `research/ronja-remote-security-r5-tls-2026-11-10` based on R4 / [PR #13](https://github.com/martintommerstigen/Baton/pull/13). Related [issue #3](https://github.com/martintommerstigen/Baton/issues/3), [PR #4](https://github.com/martintommerstigen/Baton/pull/4), [forum #6](https://github.com/martintommerstigen/Baton/issues/6), [project map B5/B2](https://github.com/martintommerstigen/Baton/blob/planning/cross-project-map-2026-11-10/PROJECT_MAP.md), [GTRCM METHOD](https://github.com/martintommerstigen/GTRCM/blob/main/METHOD.md), [RustWorld source map](https://github.com/martintommerstigen/GTRCM/tree/RustWorld). No project registry or other worker branch was changed.

## Falsifier and correction

R4's admission MAC detects forged *receipts after transmission*, but a hostile local listener could receive the bearer and the signed envelope *before* the client verifies a receipt. R5 adds an opt-in pinned HTTPS transport. The client accepts only `https://127.0.0.1:PORT` with an explicitly supplied owner-only PEM trust anchor and checks the server certificate's IP SAN before sending any HTTP Authorization header or body. The server performs TLS handshakes in the existing bounded worker pool, not the accept loop; a failed handshake releases its slot. Existing HMAC receipts and SQLite durability checks remain mandatory. No redirects, proxy, retry, shell, or UI send were added.

A wrong TLS certificate, wrong IP SAN, symlinked PEM, group-readable private key, missing pin, or pin supplied to plaintext HTTP fails closed. This does not protect against a compromised trusted TLS private key or an attacker executing with the same UID as the server. Prefer a **dedicated unprivileged service UID**; do not store secrets or keys in GitHub.

## Offline local setup — NOT executed on Greg

On the authorized service host, provision a private directory owned by the service UID with mode 0700, e.g. `/var/lib/baton-remote/private`. As that UID, generate a short-lived self-signed TLS certificate with an IP SAN, without committing its private key:

```sh
umask 077
openssl req -x509 -newkey rsa:3072 -nodes -days 30 \
  -keyout /var/lib/baton-remote/private/server.key \
  -out /var/lib/baton-remote/private/server.crt \
  -subj '/CN=127.0.0.1' -addext 'subjectAltName=IP:127.0.0.1'
chmod 600 /var/lib/baton-remote/private/server.key /var/lib/baton-remote/private/server.crt
```

Use the existing ingress CLI's required `--database`, `--token-file`, `--sender-key-file`, `--target` and `--route` flags, adding `--tls-cert-file /var/lib/baton-remote/private/server.crt --tls-key-file /var/lib/baton-remote/private/server.key`. It still binds **only 127.0.0.1**. A client on another authorized UID/host must receive an independently owner-only copy of `server.crt` in its own private directory (not the private key), and invoke the one-shot client with `--url https://127.0.0.1:8788 --server-cert-file /absolute/private/server.crt`. For a remote client, use an explicitly authorized SSH local forward and still verify the pinned TLS certificate end-to-end. Provision bearer and sender key through protected local channels, not GitHub Actions secrets. Do not make `/var/lib/baton-remote/private` group-readable to share the certificate.

The committed `deploy/systemd/baton-remote-ingress.service` template now requires TLS PEM files at `%h/.config/baton-remote/tls/server.crt` and `server.key`. Provision owner-only copies at those paths when using that template, or explicitly review/change the paths to the illustrative `/var/lib/baton-remote/private` locations above. Missing files must prevent service startup. The template remains uninstalled and unverified on Greg.\n\nTLS trust-anchor rotation is a deliberate manual step. If the server restarts with a new certificate before the client trust anchor is updated, sending fails closed and **must not be automatically retried**. Maintain the same message ID and inspect durable admission status before considering a new authorized action.

## Test classification and remaining boundaries

`python -W error::ResourceWarning -m unittest discover -s tests -p 'test_*.py' -v` includes `tests/test_http_tls_endpoint.py`, which generates ephemeral certificates using OpenSSL and tests authenticated admission, replay rejection, wrong certificate, wrong SAN, unsafe files and invalid configuration. Test keys are never checked in. If OpenSSL is unavailable, those tests skip; a green run must be inspected for skips before claiming TLS coverage.

- `tested-simulated`: only when GitHub CI has actually passed the final code.
- `implemented-unverified`: Greg service account, cert provisioning, systemd integration, TLS restart and key rotation.
- `blocked`: Greg live installation while Desktop Commander quota remains unavailable.
- **Not demonstrated:** actual A→B→C existing ChatGPT conversation wake. `accepted_not_delivered` is only durable transport admission, not source completeness or a new assistant turn.

The next falsifier is a controlled certificate rotation during in-flight admission and a TLS handshake flood that must not starve unrelated accepted work. Also verify whether the systemd unit's current `ExecStart` and `ProtectSystem` settings permit the dedicated service UID and certificate path before live installation. Preserve `PAUSE_UI_WRITES` and no blind retry.

## B5 security correction — exact leaf pin vs CA trust (2026-11-10)

The initial R5 client verified the peer against a PEM *trust anchor* and
`127.0.0.1` IP SAN before disclosure. That is sufficient when the PEM is
an uncompromised self-signed **leaf**, but it is not an exact certificate pin:
if the supplied PEM is a CA, another valid IP-SAN leaf signed by that CA
would be accepted by ordinary TLS verification. The earlier description
overstated the pinning guarantee.

The client now reads the owner-only PEM **once** to derive both the TLS
verification context and the SHA-256 digest of the *exact certificate DER*.
After a successful TLS handshake it compares the actual peer leaf DER digest
in constant time, **before any HTTP request or bearer is sent**. A mismatch
closes the socket and raises `DeliveryUncertain` (no automatic retry).
PEM bundles with multiple certificates are rejected as ambiguous. The
client therefore deliberately does **not** support CA-only trust in place
of a leaf pin. Rotate an exact leaf deliberately and update the client pin
out of band; never retry an uncertain admission without independent audit.

The one-shot CLI now defaults to `https://127.0.0.1:8788` and fails
closed if `--server-cert-file` is omitted. Legacy plaintext requires an
explicit `--url http://127.0.0.1:PORT`; it is not endpoint-authenticated
before disclosure and must not be used against an untrusted listener.

Negative control: create a local test CA, issue a *different* leaf with
the same valid IP SAN, and verify that an ordinary CA-trusting TLS handshake
succeeds while the Baton client rejects the leaf and the fake server
observes **zero Authorization headers**. Also reject multi-certificate PEM
bundles. These are offline regression tests; not evidence of a Greg-live
installation, a UI click, source completeness or an existing-chat turn.

Task IDs: B5/B2. Files: `remote_security/tls_endpoint.py`,
`remote_security/http_client.py`, `tests/test_http_tls_endpoint.py`.
Status: **implemented-unverified until the final GitHub CI run is green**.
