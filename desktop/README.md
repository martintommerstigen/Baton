# Baton Desktop v0.1

Local-first desktop client for the existing Baton relay. Requires Python 3 with Tkinter; no third-party Python packages.

Start the Baton relay locally (using existing credentials in `baton/tokens.json`):

```bash
python3 baton/server.py
python3 baton/desktop/app.py
```

Open two app windows and use the corresponding identities' tokens. The identity field is only a local label; server identity is determined by the token. Each side can send, poll, read and explicitly acknowledge messages. A relay receipt does not prove a recipient read or executed anything.

**Security:** The client permits loopback HTTP for development and HTTPS for remote endpoints. Do not publish the relay directly over HTTP or reuse demo tokens. This prototype has no end-to-end encryption, user registration, LLM provider adapters, remote pairing, or automatic command execution. Never send secrets in message bodies.

Tests:

```bash
python3 -m unittest discover -s baton/desktop -p 'test_*.py' -v
python3 -m unittest discover -s baton -p 'test_baton.py' -v
```