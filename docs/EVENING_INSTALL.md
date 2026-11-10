# Baton on Greg — evening installation boundary

This branch installs a **local command adapter**, not a ChatGPT-connected remote desktop.
It cannot be reached from a ChatGPT conversation merely because the computer is logged into chatgpt.com.

## One-time local smoke test

From a terminal on Greg, run:

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/martintommerstigen/Baton/feature/evening-local-terminal-2026-11-10/install_evening.sh)
```

The script clones to `~/.local/share/baton-evening` only if absent, does not overwrite an existing checkout, runs offline unit tests, and prints a local identity and Git revision. Inspect the script in GitHub before executing it. No login or token is requested.

## What is NOT installed

- No ChatGPT-session bridge or callable ChatGPT tool.
- No remotely reachable shell or arbitrary command execution.
- No systemd service, persistent daemon, or background browser automation.
- No proof of message delivery to a ChatGPT conversation.
- No access to Mac, 525, or RustWorld.

## Required for actual remote command execution

An explicit authenticated request/response transport reachable by the invoking ChatGPT tool, with server identity verification, authorization per operation, a command allowlist, timeouts, audit logs, and protections against replay. The existing Baton wake/UI driver can interact with an already authenticated browser page, but **it does not automatically grant the model a new terminal tool**. A bridge must be exposed through a supported connector or another user-authorized invocation mechanism. Do not expose port 8765 or browser session cookies.

## Verification levels

1. Local install: installer succeeds on Greg.
2. Local execution: the adapter prints Greg's actual identity and revision.
3. Transport: an independently authenticated request reaches Greg and returns a bound response.
4. ChatGPT access: this specific conversation can invoke that transport and observe the result.
5. Operational access: authorized RustWorld/Baton build/test tasks complete under policy.

Only levels 1–2 can be attempted with this installer. Do not describe levels 3–5 as complete.
