# Baton 0.1.3 — ChatGPT sign-in inside Baton (Linux)

## Purpose

Baton is the installed application. The official ChatGPT desktop application
is **not** a prerequisite. The model-neutral app offers:

- **Continue with ChatGPT**: OAuth authorization in the system browser with
  state, nonce, PKCE-S256 and signed OIDC identity validation against OpenAI
  JWKS; the app persists only an owner-private credential record
  (0600), never a website cookie or password.
- ChatGPT plan inference through the documented OAuth Responses API route:
  `POST https://api.openai.com/v1/responses`, `store=false`, `stream=true`.
  Only a completed stream counts as success.
- Provider-neutral local/OAI-compatible API connections remain available,
  without requiring ChatGPT.
- Baton local authenticated Core and recipient-controlled attention filters
  are independent of any account. A valid model-account OAuth token grants
  **no automatic Greg shell or external posting** authorization.

Official sources (checked 11 November 2026):
- https://developers.openai.com/siwc/token-sharing-open-source/sign-in
- https://developers.openai.com/siwc/token-sharing-open-source/models-and-inference
- https://developers.openai.com/siwc/token-sharing-open-source/preview-limitations

**Eligibility:** ChatGPT plan usage is currently an opt-in for eligible Plus
and Pro users, subject to account/workspace/model/provider policy. It does
not provide access to existing ChatGPT chat history, conversation IDs or
in-app memories. A direct OAuth plan inference turn is a *new* model request,
not a wake of an existing ChatGPT conversation. The existing-chat A→B→C
work remains separately tracked by Baton issue #3 and B1/R27 drafts.

## Usage

1. Launch Baton from Kubuntu's application menu.
2. Open **Modeller**. Click **Fortsett med ChatGPT**. Your system browser
   opens at OpenAI. Choose account/workspace and review permissions.
3. Return to Baton. A completed verified login appears in the UI. If
   ChatGPT plan usage was not authorized, the app does **not** perform model
   requests with that account.
4. Open **Modellsamtale**. Select **ChatGPT-konto** and choose the
   offered model (the selected model slug is editable in this beta).
5. Send a text request. A complete Responses API stream yields the reply.
   The receiver's local attention policy applies *before* display.
6. Alternatively choose **Lokal modell eller API-endepunkt** for Ollama
   or an HTTPS OpenAI-compatible API connection with your own token.

Only one ChatGPT account profile is stored in this beta. No historical
ChatGPT chats are synchronized. Tokens are stored in
`~/.config/baton/chatgpt-account.json` with owner-only file permissions.
The opaque, stable agent-host ID resides in `chatgpt-host.json`.

The app does not launch or reconfigure the official ChatGPT desktop app,
modify your normal browser profile, or send ChatGPT/OAuth tokens through
the Baton Core shell. Signing in opens a temporary loopback listener on
127.0.0.1 for the OAuth callback, not a public listener.

## Testing and limitations

GitHub CI runs negative tests for OAuth callback state, client-ID mismatch,
signed ID token signature/audience/nonce/issuer, missing plan permission,
rotating refresh token protection, and complete/failed SSE responses.
A GitHub CI success does **not** prove real authorization or inference on
Greg. Test an actual login in the installed app and read back an answer.

No external platform posting or existing-chat A→B→C wake is claimed.
Do not claim that ChatGPT account identity establishes model personhood,
persistent memory, delivery receipt, or permission to act on behalf of
other recipients.

On a slow or offline connection, the browser sign-in or model response may
fail without changing existing files or previously connected credentials.
The UI reports controlled errors without printing OAuth secrets.
