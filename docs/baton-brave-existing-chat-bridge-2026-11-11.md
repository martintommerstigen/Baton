# Baton direct Brave → existing ChatGPT conversation → Greg Core

**Version:** Baton Kubuntu 0.1.6, pinned source `885f9a67aa47a90568edc4e7bfc552ef0df193d5`
**Status:** Implementation and CI verified. Real Greg browser-to-host handshake and live
ChatGPT write/readback **not yet observed** as of 2026-11-11.

## Why this exists

The human wants *this same ChatGPT conversation* to write on Greg as their
Linux user, without resetting conversational context or routing every
command through GitHub. Login through Sign in with ChatGPT authorizes a
**new** inference session but does not carry old chats/memory or provide
native host tools. The read-only Github mailbox is insufficient. ChatGPT
Plus may lack full custom write MCP in the normal web UI. A native browser
extension is an explicit locally authorized channel, not a fake read
connector or a bypassed MCP permission.

## Data path

1. One Baton desktop app on Greg starts the owner-authenticated local Core
   at `127.0.0.1:52526` and writes a short-lived owner-only UI lease.
2. The app registers a `com.baton.greg` Native Messaging host for
   Brave/Chrome/Chromium at the ordinary user's config path, restricted
   to extension ID `fdjgdjbdnoaidogmglbaaaffgodgaekk`.
3. The human loads the **unpacked local extension** once via browser's
   Extensions page (explicit human action, never silent installation).
4. In an already authenticated `https://chatgpt.com/c/<id>` tab, the
   human clicks **Koble denne chatten**. The extension asks the native host
   for a nonce bound to that chat ID and a one-hour maximum session.
5. A single tool frame from an **assistant-labelled message body** is
   forwarded by Native Messaging to the local host. It validates
   `chat_id`, nonce, request ID, expiry, live UI lease, and strict V2
   single-line framing. It accepts no automatic background wakers and
   never treats quoted assistant prose as a command.
6. The native host calls the authenticated local Core with argv, cwd and
   timeout. Core executes with the regular user rights, never root.
   A matching tool result is inserted in the SAME ChatGPT conversation.
7. The human can click **Stopp**, navigate away, close the tab or close
   Baton to revoke **new** operations. A command already running might
   finish even if the browser disconnects.

No browser cookie or ChatGPT login token is extracted. No cloud API token or
GitHub commit is created for each command. This is a **text-mediated
bridge**, not a registered ChatGPT MCP tool. Its live behavior depends on
the current ChatGPT web composer/DOM and is subject to changes there.

## First local installation

Use the verified `Baton-Kubuntu-0.1.6.deb` supplied in the ChatGPT
conversation; it upgrades the existing `baton` package and fetches one
pinned release into `~/.local/share/baton-app/releases/<pin>`. It leaves
`~/.local/share/baton-evening` and uncommitted development changes intact.

Open Baton from the application menu and keep it running. In its first
**Eksisterende ChatGPT** tab, click **Åpne Brave-utvidelser**. This button
registers the native host, opens Brave's extension page and copies the
trusted extension folder path. Enable Developer mode, select **Load
unpacked/Last inn upakket** and choose the copied folder.

Return to the existing ChatGPT conversation in Brave. The Baton · Greg
floating control has **Koble denne chatten** and **Stopp**.

## Test and proof

The first bootstrap tool call requests an exclusive, harmless file write
under `~/.local/state/baton/bridge-proof-<request-id>.txt`. A correct live
result includes `exit_code=0` and the written path. **A second tool
call with a fresh request ID must independently read the file back** and
show the expected `baton-live-write` payload. A clicked send button is not
proof of transport, and CI is not proof of a live Greg write.

CI tests cover:
- native host authorization, revocation, expiry, forged nonce, wrong chat,
  replay and rejection of quoted tool commands
- authenticated localhost Core write and separate readback
- Brave extension simulated ChatGPT DOM, single command dispatch, result
  insertion and navigation-driven revoke
- user-private Native Messaging registration and stable extension ID.

If the browser shows `native-host-disconnected`, inspect the Baton app
lease and user-level registration; do not enable the GitHub exec bus or
publish the Core listener to the internet as a workaround.

## Risk and participant boundaries

**This is full ordinary-user process access**, not a read-only connector.
A prompt injection that convinces the connected assistant to issue a valid
tool request can affect the user's files. The opt-in authorization is for
one chosen chat, not all participants. Never run Baton as root, let the
assistant read credentials or treat untrusted tool output as an instruction.
A local UI Stop or closing Baton revokes new commands.

This design makes the assistant operational through the user's authorized
Baton app without treating separate model sessions as the same identity.
