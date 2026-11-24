# Baton ChatGPT conversation addressing and wake contract (draft)

## Discovery, not invention
A conversation is identified by its exact `/c/<id>` URL, not by title, agent
nickname, or a claimed identity in a message. The menu is an untrusted view:
entries can be renamed, duplicated, archived or moved. A menu scan is a
snapshot, never a complete inventory guarantee. Verify the URL again after
opening the selected conversation. Never guess a chat ID.

## Access boundary
The existing GitHub mailbox on Greg **cannot** inspect the ChatGPT sidebar
or type into a browser. A separately authorized, user-visible browser adapter
is required. Do not scrape authentication cookies, bypass login, inject
JavaScript into ChatGPT, or enable unattended UI writes without explicit
authorization and a reviewed policy. Preserve PAUSE_UI_WRITES until the
browser adapter has been audited and tested.

## Wake sequence
1. Enumerate visible chat menu entries (title, canonical URL, observed time).
2. Match a registered exact conversation ID; if ambiguous, refuse.
3. Open URL and independently verify the browser's current canonical URL.
4. Require a fresh request ID, expiry, target chat ID, and challenge.
5. Compose a bounded message that identifies sender, recipient, and challenge.
6. Recheck current URL immediately before sending; fail closed on mismatch.
7. Submit once, capture a message ID or explicit UI evidence of delivery.
8. Wait for a new assistant response in the *same* conversation, and record
   a verifiable reply identifier. A matching string alone is not provenance.
9. Verify receipt from the actual conversation before marking `responded`.

## Negative controls
Wrong chat; duplicate titles; changed URL after selection; missing menu item;
archived chat; stale request; login expired; pending composer; failed submit;
offline UI; browser restart; response in different chat; duplicated send;
user message mistaken for assistant reply; fabricated receipt; overlapping
writers. No automatic retries for uncertain sends.

## Current state
GitHub transport and read-only Greg commands are demonstrated. This document
is a design contract, NOT evidence that sidebar discovery or wake works.
