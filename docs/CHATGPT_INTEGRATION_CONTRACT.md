# Baton ↔ ChatGPT: integration contract

## Two separate sign-ins

1. **Sign in with ChatGPT** (SIWC) identifies the human Baton account
   when OpenAI has enabled the relevant integration. It does **not**
   authenticate individual ChatGPT conversations or grant access to them.
   Never copy ChatGPT cookies or browser session tokens.
2. **ChatGPT → Baton** uses a custom authenticated MCP app with OAuth
   authorization-code + PKCE. Baton is the protected resource and verifies
   issuer, audience, expiry and scoped permissions on *every* tool request.
   The OAuth subject identifies the authorized Baton user, **not** an
   independently verified ChatGPT conversation ID.

Official references:
- https://developers.openai.com/plugins/build/auth
- https://developers.openai.com/siwc/quickstart
- https://help.openai.com/en/articles/12584461-connecting-custom-mcp-servers-in-chatgpt

## Required components before enabling write access

- Register Baton as a supported SIWC client if eligible, or use a separately
  configured OAuth identity provider for the Baton MCP authorization server.
  **Do not invent OpenAI client IDs or endpoints.**
- Expose the Baton MCP protected resource over authenticated HTTPS or an
  approved private tunnel. Never expose the Greg Unix execution socket.
- Publish protected-resource and OAuth authorization-server metadata, support
  PKCE S256, refresh-token lifecycle, and reject invalid token audience,
  issuer, scope, expiration or signature.
- Implement MCP tools `greg_status`, `greg_exec`, and `greg_job_status`.
  Tools must validate authenticated principal and explicit authorization.
  A model-provided `conversation_id` is an untrusted label unless backed
  by an independently verifiable platform assertion.
- Grant `greg:exec` separately from account sign-in. Require user approval
  for initial broad write privilege and allow immediate revocation.
- Dispatch to `AuthenticatedGregDispatcher` with a signed, unique job ID.
  Maintain per-user audit records; no automatic retry of uncertain writes.
- Route to the local dedicated caller UID, then to the Greg executor socket.
  Keep the existing PAUSE_UI_WRITES rule for ChatGPT UI automation.
- Verify with an actual ChatGPT tool call, then a harmless write/readback
  on Greg, then revoke permission and verify denial.

## Current implementation status

`remote_security/chatgpt_greg_dispatch.py` authenticates a **shared-secret
job envelope**. It is not an OAuth token verifier or MCP server. The
`remote_security/greg_executor.py` process executes locally under the Greg
user; it is not a network endpoint. The installer does not create the OAuth
provider or establish an authenticated ChatGPT connection.

Do not claim that logging into Baton with a ChatGPT account automatically
makes every existing ChatGPT conversation callable or grants it host access.
MCP tools must be connected and enabled in the ChatGPT product, subject to
account/workspace feature availability.
