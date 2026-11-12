# Greg live capability probe — 2026-11-11 16:24 UTC

Scope: the existing `GTRCM:transport/baton-greg-bus-2026-11-10` mailbox, not a direct MCP client, not a browser wake, and not an installed H26/R27 observer. No Desktop Commander call, service mutation, token read, UI Send, or arbitrary shell execution.

## Observed requests and receipts

1. `install-status` request `b9c312f18a07f90957c8386d1bc93bb3` was created at `2026-11-11T16:24:08.750Z` on the private mailbox branch. The Greg worker returned `{"id":"b9c312f18a07f90957c8386d1bc93bb3","reason":"ValueError","status":"rejected"}`. This is a **negative live capability result**: the responding worker does not currently accept the PR #64 operation. It does not establish whether the inspector file is present elsewhere on disk or whether the graphical Core is running.

2. A fresh allowlisted `git-revision` request `2e582c98346f2130b9a5a8fa62c50aaf`, created at `2026-11-11T16:24:26.450Z`, returned `status=executed`, `exit_code=0`, `ok=true`, `output=dba722a48f21da4d58c4de0fc8dba395da13698e`. This is **positive live transport evidence**, and identifies the checkout revision used by the worker, not a proof of the active GUI or service binary.

These are direct worker-generated receipts, not synthetic GitHub CI artifacts. The existing bus is operational; the new read-only inspection operation is **source-only, not deployed**.

## Source-linked evidence

- [Rejected install-status request](https://github.com/martintommerstigen/GTRCM/blob/transport/baton-greg-bus-2026-11-10/.baton-greg-bus/requests/b9c312f18a07f90957c8386d1bc93bb3.json) and [Greg rejection receipt](https://github.com/martintommerstigen/GTRCM/blob/transport/baton-greg-bus-2026-11-10/.baton-greg-bus/responses/b9c312f18a07f90957c8386d1bc93bb3.json) (private GTRCM).
- [Successful revision request](https://github.com/martintommerstigen/GTRCM/blob/transport/baton-greg-bus-2026-11-10/.baton-greg-bus/requests/2e582c98346f2130b9a5a8fa62c50aaf.json) and [Greg receipt](https://github.com/martintommerstigen/GTRCM/blob/transport/baton-greg-bus-2026-11-10/.baton-greg-bus/responses/2e582c98346f2130b9a5a8fa62c50aaf.json).
- [Baton PR #64](https://github.com/martintommerstigen/Baton/pull/64): `install-status` allowlist source, not a deployed worker.

## GTRCM evidence boundary

- **JA**: one specific request was accepted, executed and returned a revision by the responding Greg worker.
- **NEI**: that worker rejected the new `install-status` operation.
- **ikke-NEI**: Core process ownership, UI lease, MCP client exposure, authenticated model participation, and existing-chat A→B→C wake are still unobserved.

Do not interpret the negative capability response as authorization to bypass the worker's allowlist or to install a second Baton. Retain the single-installation contract. Next step requires reviewed, explicitly authorized update of the existing checkout/worker, followed by a fresh bounded read-only manifest; never blind `reset --hard`, never claim deployment from CI.
