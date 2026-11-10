# Baton embedded ChatGPT ↔ Core bridge (experimental)

## Goal
ChatGPT runs inside Baton's Qt window. Baton native Skin calls the already-running local Core API on 127.0.0.1:52526 with a private local token. No GitHub command relay or cloud reverse proxy.

This is not a native ChatGPT/MCP tool registration. It is an opt-in text protocol read from assistant-labelled ChatGPT conversation turns.

## Live activation on Greg
1. Update the Baton worktree and restart run_baton_chatgpt.sh.
2. Select one existing ChatGPT conversation from the sidebar; the address must have its exact /c/<id>.
3. Click Aktiver modellverktøy i åpen samtale in the native Baton panel.
4. Baton sends a bootstrap message to that same conversation; ChatGPT may reply with a BATON_TOOL_V1 framed command for hostname.
5. Baton forwards the structured argv/cwd/timeout call to the already running local Core, then tries to return BATON_TOOL_RESULT_V1 to the same chat.
6. Stopper: use Stopp verktøyøkt. Navigation to a different conversation also disables the session.

## Evidence boundaries
CI success proves tests pass, not that the full live round trip works. A send-button click is not durable delivery. A rendered assistant turn is UI observation, not cryptographic provenance. A completed A→B→C wake requires actual independent replies from each specified existing conversation.

## Security
Enabling this bridge permits full Greg user-level commands requested by assistant output from the selected chat. Prompt injection remains a risk; enable only in trusted conversations. Do not run as root. No cookies or local API bearer token enter the ChatGPT page. Command output up to 2400 characters is sent back into the conversation and may be sensitive. The composer must be empty before Baton sends; wrong chat, duplicate request or uncertain sends fail closed. No automatic resend.

## Known limitations
ChatGPT site DOM selectors may change. Automatic message sending and Core tool call acceptance require testing on Greg. The bridge does not itself provide ChatGPT-native tools or A→B→C unattended conversation waking.
