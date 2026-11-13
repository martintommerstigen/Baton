---
name: baton-greg-bridge
description: Use when the user asks to connect an existing ChatGPT conversation to the Baton application on Greg; run bounded diagnostics, verify mailbox receipts, or plan/verify a separately authorized tool connection without starting a blank ChatGPT model session.
---

# Baton Greg bridge — existing conversation, bounded live transport

The purpose is to let the **currently invoked ChatGPT conversation** use Baton and preserve its existing conversation context. DO NOT sign in to a new model session, suggest uploading chat memory, or say a model API invocation is a continuation of an existing ChatGPT chat. This skill adds an operational workflow using the already connected GitHub plugin. It is not a new MCP device tool and does not itself grant shell access.

## Choose the actual route before concluding access is absent

The GitHub diagnostics route below is one limited adapter, not an inventory of all tools available to this conversation. For internal Baton discussions or a received `baton://` link, read the sibling [Baton discussion workflow](../baton-discussions/SKILL.md). It contains the separately demonstrated Greg route and its constraints. A missing native Baton tool is not proof that an already authorized terminal/browser transport is absent. Discover available tools and inspect the actual device/source before making an access claim. This plugin itself grants no access and does not turn a previous denial into a current permission.

## Actual source and current scope

- GitHub repo: `martintommerstigen/GTRCM`, branch `transport/baton-greg-bus-2026-11-10`.
- Read-only mailbox input path: `.baton-greg-bus/requests/<id>.json`.
- Response path: `.baton-greg-bus/responses/<id>.json`.
- Baton handler source: `martintommerstigen/Baton`, `feature/evening-local-terminal-2026-11-10`, `baton_github_bus.py`.
- Supported **by-default** operations: `identity`, `system`, `git-revision`, `python-version`; they contain no argv/cwd/timeout fields.
- Real result observed on 2026-11-11: `identity` executed on Greg (user `olliver`, exit 0) with request ID `e514b87bd3f34030ad9e09e4867fa2c1`.
- Real result observed: **opt-in `exec` denied**, request `9634c7a2e7f94c3299871b0b4a9e8ad1` returned status `rejected`, reason `ValueError`. This skill MUST NOT imply full shell access is enabled or try to work around the check.
- This is a GitHub mailbox relay, **not** direct local MCP and **not** a confirmed wake of a different existing ChatGPT conversation.

## Procedure for safe read-only operation

1. Use the connected GitHub tool to verify marker `.baton-greg-bus/README` contains `BATON-GREG-BUS-V1` on the exact source branch. Verify desired operation is in the current source-defined allowlist.
2. Generate one fresh lowercase 32-character hex request ID and one UTC ISO-8601 `created_at`. Create a JSON file with exactly three fields `id`, `operation`, `created_at` on the transport branch. Use GitHub `create_file` (create-only); **never overwrite** a request.
3. Inspect `.baton-greg-bus/responses/<id>.json` on that branch. The local daemon may poll periodically. The result must match the exact ID and operation and indicate `status=executed`. Read the nested tool result; check actual `ok` and `exit_code` before claiming anything ran. Never interpret GitHub commit alone as execution. If no response, say pending/unconfirmed. If `rejected`, preserve the exact reason without retrying blindly.
4. Protect credentials and message contents. Never send raw ChatGPT transcripts, cookie jars, private tokens, or unknown local paths into a repository branch. This relay is not a general-purpose archive.
5. Any command-style `exec` is NOT enabled by default. Require separate verified local owner consent, verified transport admission, and non-root scope before trying a harmless command. Never auto-enable `--enable-exec`, silently modify the daemon's service flags, or bypass Baton Core policies. Preserve source provenance and read back any approved write separately.

## Integration roadmap / limitations

The complete product calls for a registered plugin/MCP tool exposed to **this same conversation** backed by Baton's authenticated Core, with owner-approved capabilities. A local STDIO MCP process alone cannot become a web-chat tool without an actual supported local host or a verified authenticated HTTPS MCP/tunnel connection. Never fabricate endpoints, tunnel IDs, tool availability, model identity, access to prior ChatGPT threads or receipt of external messages.

If a user asks for full local write access, inspect the available connected tools and the actual Baton source; implement the supported authenticated connection in the repo, and distinguish code/CI from live Greg deployment. If the host does not expose an actual Baton execution tool, do not claim one exists. Creating this plugin is not proof of live `greg_exec` tool discovery.
