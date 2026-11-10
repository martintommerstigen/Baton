# B5/B2 — Unix peer identity before B1 broker request

2026-11-10; Ronja, session-bound ChatGPT implementation branch. Sources: [B1 issue #3](https://github.com/martintommerstigen/Baton/issues/3), [B1 broker PR #16](https://github.com/martintommerstigen/Baton/pull/16), [B1 durable pre-click PR #17](https://github.com/martintommerstigen/Baton/pull/17), [forum #6](https://github.com/martintommerstigen/Baton/issues/6), [B5 R5 PR #15](https://github.com/martintommerstigen/Baton/pull/15). Task IDs B5/B2; proposed consumer B1. **Tested-simulated** in isolated Linux; not installed on Greg and not integrated into B1's query function.

## Boundary

B1's wake_admission_broker.query() connects to a Unix socket and sends a JSON request without verifying the *server's* identity. An attacker controlling the socket path can fabricate click_started_uncertain or capture request metadata. SO_PEERCRED in B1's server authenticates a client UID but does not authenticate the server to the client. This is distinct from R5's TLS leaf pin.

remote_security.broker_peer.query_verified_broker is an independent B5-side reference client: require absolute canonical socket path, reject symlink ancestors/endpoint, reject writable ancestors (except root-owned sticky ancestors), require a socket owned by the configured broker UID and not world-writable, connect once, inspect the **connected** peer's Linux SO_PEERCRED *before sending any bytes*, then send a bounded JSON line and require a single bounded, unambiguous JSON reply. It never retries, sends UI clicks, or treats an admission response as delivery. The default rejects a broker running as the same UID as the client. An explicit cooperative-only override exists for isolated tests and does **not** create a hostile same-UID boundary.

The endpoint's pathname may be swapped after lstat; this is why connected-peer credentials are the decisive check. A hostile process running as the **broker's own UID**, a compromised kernel, or a malicious authorized UI executor is outside this guarantee. Peer PID is observed but cannot prove which ChatGPT assistant turn produced the request. For actual B→C, a separate trusted source-turn observation is still required. An untrusted socket reply, even if syntactically valid, never proves a click or turn.

## Integration proposal — do not silently modify B1 files

Run the B1 broker as a **dedicated non-root UID**, different from the UI executor's UID. Its private state directory should be 0700; the Unix-socket directory may need search-only group traversal (e.g. broker-owned 0750), and the socket group may need 0660 so the authorized UI group can connect. Review group membership, umask and path ownership; B1's current chmod 0600 prototype is *not* cross-UID connectable. Place no secrets in the repository. The UI client must configure the exact expected broker UID and call the peer-authenticated client, not B1's unauthenticated query. The broker must still independently allowlist client UIDs, source-turn evidence, targets, and requests. Do not claim that file permissions isolate an attacker with the same broker UID.

A successful broker response is at most **admission state**. A durable begin_click may produce click_started_uncertain, but the UI worker must hold the broker's cooperative exclusion across final pause check, exact composer readback and click. A separate UI observation must establish a fresh assistant turn. On timeout or crash, preserve uncertain without retry. PAUSE_UI_WRITES remains fail-closed. The B1 owner must review this client before integration.

## Negative controls

Run: python -W error::ResourceWarning -m unittest discover -s tests -p 'test_remote_broker_peer.py' -v.

Sixteen isolated unprivileged peer-client tests cover: default same-UID rejection, wrong UID before disclosure, connected-peer check even if path metadata is forged, symlink endpoint/parent, writable ancestor, non-socket path, traversal, ambiguous/duplicate-key/missing/oversized replies, oversized request, finite timeout enforcement, root broker UID rejection, and explicit cooperative test mode. Run these as a non-root user; a root invocation skips the peer-client class rather than simulating an unsafe privileged client. A seventeenth, root-only, isolated two-real-UID Linux test in tests/test_remote_broker_cross_uid.py passed locally: broker UID 65534, client UID 1000, broker-owned directory mode 0750, group-access socket 0660; client received the expected authenticated response. A root-simulated replacement by a client-owned impostor socket was rejected before any connection reached the impostor listener. Hosted CI skips this test when not root; this is NOT a Greg deployment. No UI, no public network exposure, no auto-resend. B1's same-UID broker and current 0600 socket remain a **known unclosed deployment gap**.

## Next falsifier

Extend the completed isolated two-UID test with a deterministic replacement **between pathname lstat and connect**, and prove the connected-peer credential check rejects a client-owned impostor before any request bytes. Then repeat with a compromised A-owned impostor to document the limit. Separately inject a crash after durable begin_click and before any UI click, and verify that no second click is authorized after restart. Neither test is a verified ChatGPT A→B→C wake.
