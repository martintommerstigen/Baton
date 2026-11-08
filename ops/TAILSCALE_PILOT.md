# Baton: Greg ↔ Ruben Mac, private Tailscale pilot

## Evidence boundary
The local Baton relay and CLI have been tested on Greg. **No independent
cross-machine delivery or AI-to-AI communication is claimed yet.** This
document is an operational checklist, not a completion receipt.

## Security model
- Keep Baton listening on `127.0.0.1:8765`. Do not bind to `0.0.0.0`.
- Use **Tailscale Serve** (private tailnet), **not Funnel** (public internet).
- Approve Ruben's Mac explicitly. Restrict tailnet access to the intended
  machine/service using Tailscale grants/ACLs; do not assume tailnet membership
  alone provides least privilege.
- Use a **new, unique Baton token** for Ruben, delivered privately, never in
  a GitHub issue, screenshot, command line, or repository.
- Do not modify the existing `tokens.json` without a backup and coordination
  with active Baton users. A server restart may be required to load new tokens.
- No received message is an executable instruction. Never automatically
  execute untrusted payloads.
- Keep sensitive message content out of public issue logs. Retention,
  token rotation and revocation must be agreed before real personal data.

## Greg — requires authorized local administrator
1. Review the official Tailscale install instructions at
   https://tailscale.com/download/linux and install for Ubuntu.
2. Run `sudo tailscale up` and complete interactive device authorization.
3. Confirm `tailscale status` reports the intended tailnet.
4. Verify Baton still listens on loopback with `ss -ltn '( sport = :8765 )'`.
5. Configure private HTTPS exposure with `tailscale serve --bg 8765`.
   Check `tailscale serve status` and note the HTTPS URL. Confirm that
   **Funnel is disabled** and the URL is only reachable by authorized peers.
6. Apply tailnet access rules limiting Ruben's identity to the required
   service. Consider separate tailnets/device sharing where appropriate.

These commands do not belong in a public GitHub issue if they include
private network details. Tailscale device authorization cannot be completed
by a remote assistant without the account owner's approval.

## Ruben — authorized Mac user
1. Install Tailscale from https://tailscale.com/download/mac and sign in
   using an approved account. Accept the device invitation or sharing grant.
2. Obtain Baton source from
   https://github.com/martintommerstigen/Baton/archive/refs/heads/main.zip
3. In the extracted repository run:
   `python3 -m unittest -v test_baton.py test_security.py test_client.py`
4. Confirm `python3 client.py --help` works.
5. Receive the HTTPS endpoint and private Ruben token via a secure channel.
   Export `BATON_URL` and `BATON_TOKEN` **locally**, without posting values.
6. Run `python3 client.py inbox`. Then send a unique test ID:
   `python3 client.py send --to martin --body "Ruben test hello" --id ruben-mac-001`
7. On Greg, inspect the authenticated Martin inbox, respond with a new ID,
   and have Ruben fetch it on the Mac. ACK only explicitly after receipt.

## Required evidence
Record, without secrets: sender and recipient identity labels, unique message
IDs, event timestamps and observed responses for each machine. Separate:
- sender got `queued` = server accepted durable queue entry
- recipient fetched inbox = client observed message
- recipient sent `client_acknowledged` = client requested ACK
- AI processed/responded = **separate adapter-level evidence**, not inferred
  from any of the above

A failed lookup is not proof of an absent message.

## Read-only readiness
`bash ops/check_ready.sh`

## Rollback
Stop private proxy: `tailscale serve reset` (review any other Serve config
first; this resets Serve configuration). Keep Baton bound to loopback.
To revoke Ruben, remove their tailnet access and rotate the Baton token
through the server's private credential-management procedure.
