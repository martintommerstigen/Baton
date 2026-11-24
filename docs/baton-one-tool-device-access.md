# Baton device access: one tool, one local Core (2026-11-11)

## Decision

An existing ChatGPT conversation does not need a separate model session or a
raw filesystem connector. It needs **one honestly represented, authenticated
action gateway** to the user's own Baton Core. A single `greg_exec` action
already has the power to operate on Greg at the configured Linux user scope.
The narrow client interface and the broad host capabilities are distinct
layers, and the human must be able to revoke the connection.

**Important:** a tool that causes file writes or process execution is a
*write/action* capability even if the tool is named 'read', 'status' or
'queue'. Never disguise writes as reads to evade client permissions.
The ChatGPT client must authorize the real action. GitHub files used as an
intermediary do not make an action read-only or eliminate the host risk.

## Supported current paths

1. **Preferred once supported by the selected client:** existing ChatGPT
   conversation -> correctly registered Baton MCP action -> local authenticated
   Baton Core -> ordinary user permissions. A private Secure MCP Tunnel can
   carry MCP traffic, but requires client/workspace support and a real tunnel
   connection. A tunnel does not itself authorize tool use.
2. **Baton beta for existing ChatGPT Plus web chats:** open the existing
   ChatGPT conversation INSIDE the unified Baton desktop app, manually enable
   the in-chat tool bridge, and let Baton execute the verified request against
   local Core over loopback. The live chat keeps its history; GitHub is
   excluded from execution transport. This is DOM- and text-mediated, NOT a
   native ChatGPT MCP tool and not validated as reliably wake-capable.
3. **Developer fallback only:** the GitHub bus currently handles bounded
   read-only operations. It is not recommended for normal runtime traffic.

## Authority and provenance

The core never runs as root. It uses an owner-private token and loopback
listener. The desktop bridge binds authorization to an exact chat ID,
a fresh per-session nonce and a single-use request ID, and refuses to execute
instructions inferred from user quotes or arbitrary page text. Tool results
are returned with a matching ID, and writes require separate verification.
A user can stop the bridge without closing their conversation.
No host-write privilege is obtained just from OAuth 'Sign in with ChatGPT'.

Explicit choice of one participating conversation must not automatically
authorize all other chats, models or inbound contacts. Incoming text and
webpage content are untrusted data. Baton's Core authorization must enforce
per-channel scope and retain enough provenance for correction.

## Evidence and acceptance

- CI validates the text-protocol parser, client routing, and non-automatic
  activation of the bridge. These are *source/CI* results.
- A real Greg acceptance test requires launching the new existing-chat tab,
  signing into its isolated browser profile if needed, selecting a known
  existing /c/ conversation, clicking Activate, and observing:
  (a) that same chat's existing context;
  (b) a unique tool request;
  (c) matching Core exit code;
  (d) independent readback after a harmless file write.
- The current GitHub read-only mailbox has proven a live `identity`
  operation on Greg. A later `exec` request was **rejected**; no live write
  through that mailbox is claimed.
- Native custom MCP write availability is product/plan-specific. As of this
  review the documented Plus path must not be assumed to expose arbitrary
  write actions. Never mislabel a side-effecting tool as a read action.

Sources:
- https://developers.openai.com/api/docs/guides/custom-mcp-server
- https://developers.openai.com/api/docs/guides/secure-mcp-tunnels
- https://help.openai.com/en/articles/12584461-developer-mode-and-full-mcp-connectors-in-chatgpt
