# No-Greg deployment decision (2026-11-10)

## Objective

Wake existing ChatGPT conversations A→B→C without installing software on Greg, without manual copying, with real chat/turn receipts.

## Verified platform boundaries

- GitHub Actions runs Baton tests and offline simulations. It has no authenticated ChatGPT browser. A GitHub webhook is not a ChatGPT chat turn.
- ChatGPT scheduled and event-triggered tasks can run in the cloud and respond to GitHub events, but no documented feature was found that injects a message into any arbitrary historical ChatGPT conversation ID.
- ChatGPT Work cloud browser can interact with supported signed-in websites and continue after the user leaves. It is the most promising authorized no-Greg environment for testing existing-chat UI interaction, subject to site restrictions and permissions.
- A ChatGPT dot can use its own cloud computer if enabled for the account; this does not establish an arbitrary historical-chat injection API.
- API conversation IDs are not interchangeable with existing historical ChatGPT product conversation IDs.

## Required live experiment in Work

1. Authorize cloud-browser access to the user's ChatGPT account if supported.
2. Navigate to three already existing chat URLs A, B and C. Never create replacement chats.
3. Inspect read-only: confirm all three load, assistant turns can be identified, and UI interaction is allowed.
4. Observe a fresh explicit wake request from existing A, then send a uniquely marked harmless message to existing B and verify B's actual assistant turn.
5. Only on an explicit allowlisted B request, send to existing C and verify C's actual assistant turn.
6. Persist source and target conversation IDs, turn IDs and uncertainty state; repeat without duplicate sends.

Stop if Work cannot access the site, target existing chats, or verify turn identities. Do not substitute GitHub task runs or a new model worker.

## Deployment separation

The repository's run_chatgpt_wake_chain.py requires an already authenticated Chromium CDP session and three open tabs. GitHub Actions alone cannot satisfy those prerequisites. Work cloud browser is not exposed as a CDP endpoint to this repository, so Work must perform the authorized interaction directly, rather than pretending this Python runner is executing there.

## Sources

https://help.openai.com/en/articles/20001280-using-cloud-browser-in-chatgpt
https://help.openai.com/en/articles/10291617-scheduled-tasks-in-chatgpt
https://help.openai.com/en/articles/20001530-getting-started-with-your-dot

This is an acceptance specification, not proof of a completed live wake.
