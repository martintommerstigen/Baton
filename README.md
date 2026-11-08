# GTRCM Baton v0

Independent Python-standard-library relay. No ChatGPT integration is claimed.

## Local start

`python3 server.py --host 127.0.0.1 --port 8765`

The private `tokens.json` has one 32+ character bearer token per participant. Never commit or send this file. Create distinct secrets with `secrets.token_urlsafe(36)`.

## API

All requests use `Authorization: Bearer <token>`.

- `POST /v1/send` with JSON `{"id":"unique-client-id","to":"ruben","body":"Hello"}`. Response `queued` (or `already_queued` on retry) is **not** proof of receipt.
- `GET /v1/inbox` returns unread messages addressed to the bearer identity.
- `POST /v1/ack` with `{"id":"unique-client-id"}` marks the message acknowledged by the authenticated client. This does **not** prove a human or an AI processed it.

## Security and limitations

- Loopback HTTP only. For remote access, use a properly authenticated TLS endpoint / VPN with rate limits and secret rotation; **do not** expose port 8765 directly.
- No ChatGPT app push, no API model loop, no iPhone background agent, no end-to-end encryption, no multi-tenant policy, no message expiration, no delivery-to-chat proof.
- SQLite is durable on the host; messages are stored in plaintext on Greg. Use separate consent and retention policies before involving another person's data.
- `tokens.json` and `baton.sqlite3*` must stay private.
- This prototype is isolated from Rolf's active mailbox.

## Tests

`python3 -m unittest -v test_baton.py test_security.py test_client.py`

## Lifecycle clarification (ACK-02)
New sends return `queued`; identical retries return `already_queued` or `client_acknowledged` if the recipient previously called `/v1/ack`. `/v1/ack` returns `client_acknowledged`, **not** proof of durable local storage, model processing, or human reading. A client that ACKs before durable storage can lose a message on crash. This reliability gap remains open; do not use this prototype for important delivery guarantees.

## Exactly-once boundary (CRASH-03)
Baton provides stable message IDs and replayable delivery attempts; it does **not** guarantee exactly-once processing or external effects. Local Core state may be deduplicated transactionally. An external non-idempotent effect cannot be made exactly-once by local dedup alone across a crash boundary. Use cooperating downstream idempotency/atomic transactions, or preserve an `unknown` outcome for reconciliation. Do not blindly retry irreversible operations.

## Independent command-line client (Mac/Linux)

`client.py` uses only the Python standard library and does not execute received text.
For a **local** relay, set `BATON_URL=http://127.0.0.1:8765` and set
`BATON_TOKEN` to your own private token (never put it in GitHub issues).

```sh
python3 client.py inbox
python3 client.py send --to martin --body "Hello from Ruben" --id ruben-001
python3 client.py ack --id martin-001
```

The client requires HTTPS for non-loopback endpoints. **There is no public Baton
endpoint yet**, and these commands do not establish access to Greg by themselves.
The `send` receipt confirms server queueing only; `inbox` never automatically ACKs.
Do not post real credentials, private network addresses, or personal messages in public issues.

To verify locally without contacting Greg:
```sh
python3 -m unittest -v test_baton.py test_security.py test_client.py
```

This proves a two-identity exchange within a local test process, not communication
between independent machines or AI agents.
