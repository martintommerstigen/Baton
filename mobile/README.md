# Baton Mobile v0.1 — Android browser prototype

Start the existing Baton server locally: `python3 baton/server.py`. Open `http://127.0.0.1:8765/mobile` on the **same computer** for a local smoke test. On Android, use a properly authenticated HTTPS reverse proxy or trusted tunnel to the loopback-only Baton server; do not expose port 8765 directly. No public endpoint or Ruben account has been provisioned.

The token stays in JavaScript memory for the current page only. It is not stored in localStorage, cookies, or URLs. Each participant needs their own separately provisioned token and identity. This version supports text-only send, inbox and explicit acknowledgement. It does not connect to Rubens LLM or automate any app. Do not send credentials or sensitive data in messages.

Tests: `python3 -m unittest discover -s baton/mobile -p 'test_*.py' -v`.