# Baton as a direct MCP tool in ChatGPT Linux desktop

## Purpose

Use Greg's actual files and commands without printing BATON_TOOL_V1/V2 commands
inside the ChatGPT conversation. The model invokes the MCP tool `greg_exec`
through the official Linux desktop client's local Codex MCP host.

This integration is separate from the QtWebEngine **embedded ChatGPT website**.
That hosted webpage cannot automatically discover a local MCP server just
because Baton has been launched.

## Architecture

- Official ChatGPT Linux desktop app / Codex MCP host
- Local STDIO MCP subprocess: `baton_mcp_stdio.py`
- Native Baton client: `baton_core_client.execute_on_greg`
- Authenticated loopback request: 127.0.0.1:52526
- Baton Core: ordinary Greg user-level `argv` execution (not root)

Baton must be running in its native Qt UI. The UI publishes a local process
liveness lease, and the MCP subprocess **refuses tool executions if the lease
is absent, stale, world-readable, or belongs to a dead process**.
The Core itself keeps its private 0600 bearer token; that token is never
stored in ChatGPT config, command arguments, or chat content.

The existing V1/V2 text protocol remains legacy-only for the embedded browser.

## Recommended one-command launcher

After updating this repository, run as `olliver` on Greg:

    bash run_baton_direct.sh

This opens a
small dedicated **Baton Core** window. Keep that window open while using the
**official ChatGPT Linux desktop app**. This route does NOT open the hosted
ChatGPT website inside QtWebEngine or inject BATON_TOOL_V2 messages.
Closing the small Core window revokes the local MCP liveness lease. The
ordinary-user Core listener is loopback-only.

MCP registration is now an explicit option, NOT a prerequisite to running
Baton. To configure the supported Codex-side local MCP host, run:

    BATON_REGISTER_MCP=1 bash run_baton_direct.sh

The first-time install of the official ChatGPT desktop application is a
separate user action. Get the official package from
https://learn.chatgpt.com/docs/linux/linux-app, sign in and restart the app
after registering the MCP server. Open Settings → MCP servers and verify
`baton_greg`.

If GitHub created the launcher without an executable bit, use
`bash run_baton_direct.sh`, not `./run_baton_direct.sh`.

## One-time registration on Greg

1. Download/install the **official** ChatGPT Linux desktop preview. Ubuntu
   24.04/26.04 LTS, Debian 13 and certain other distributions are supported;
   Kubuntu compatibility depends on its Ubuntu base and is not guaranteed.
   See https://learn.chatgpt.com/docs/linux/linux-app
2. Update Baton:

       cd ~/.local/share/baton-evening
       git pull --ff-only origin feature/evening-local-terminal-2026-11-10

3. Run the registration once, as Greg's normal user:

       python3 install_baton_desktop_mcp.py

   This safely appends a named `[mcp_servers.baton_greg]` entry to
   `~/.codex/config.toml`, using the absolute path of the checked-out
   `baton_mcp_stdio.py`. It leaves all other TOML settings intact.
   If that entry already exists and differs, it refuses to overwrite it.

4. Launch and leave the **Baton app** running:

       bash run_baton_direct.sh

   `run_baton_chatgpt.sh` is the previous embedded-website/text-protocol
   experiment; do not run it as a second concurrent production UI.

5. In the **official ChatGPT desktop/Codex client**, restart it after
   registration and inspect MCP availability in the supported client.
   The `~/.codex/config.toml` entry configures the **local Codex MCP host**;
   this alone does not establish tool access in every ordinary ChatGPT
   conversation. Client support and policy must be verified in the actual
   session.

6. Ask for an innocuous test: "Use the `greg_exec` tool to run
   `/usr/bin/hostname` on Greg, then write `BATON-MCP-WRITE-OK` to
   `~/baton-mcp-proof.txt` and read it back."

When the verified client exposes `greg_exec`, its tool UI handles
invocation and results. There is no need to type BATON_TOOL_V2 in that
client. Until a live result is observed on Greg this is not verified
end-to-end. With the user's explicit one-time authorization, the generated
config uses `default_tools_approval_mode = "auto"`, which is powerful.
If per-tool confirmation is preferred, change this to `"prompt"`.
OpenAI client policy can still require its own approvals.

## Real tests

- `test_baton_mcp_stdio.py` verifies tool behavior, error propagation, and
  denial when Baton UI is not running.
- `test_install_baton_desktop_mcp.py` preserves previous config, refuses
  conflicts and symlinks, and performs an **authenticated write plus separate
  readback through MCP → Baton Core** in CI.
- `test_baton_desktop_lease.py` verifies live PID/starttime, stale lease
  rejection, private permissions and cleanup.

A CI pass on another machine is **not** proof this integration has been
configured or exercised on Greg; test it in the official desktop application.

## Safety and limitations

This tool can modify and delete any user-writable file, run git commands, or
execute other processes as Greg's normal account. Keep backups, protect
credentials, and avoid using the tool in conversations containing untrusted
instructions. Never run as root. Closing Baton UI closes its Core lease;
already-running commands may still finish. The private loopback Core has no
internet listener.

The MCP configuration is local to Greg's ChatGPT desktop/Codex host. ChatGPT
web and the QtWebEngine embedded webpage don't load this config, and the
MCP registration is not automatically available in those contexts.
