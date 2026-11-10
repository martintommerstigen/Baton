# B1/B5 broker-gated UI boundary — offline implementation (2026-11-10)

**Source gate:** [277-branch metadata delta and prior-work check](2026-11-10-b1-broker-ui-history-gate.md). This is an implementation of an already identified gap, not new physics or a complete history audit.

## Change

`ChatGPTUIDriver.submit_once(..., before_click=...)` now accepts an optional explicit pre-click gate, invoked **after** target allowlist, existing URL, empty draft, exact composer readback, send-button and pause preflight, but **before** `send.click()`. The gate is not invoked on a known preflight rejection. After the gate, the driver checks URL, pause, send enabled and exact composer again; any failure at that point is **uncertain**, not `PreSubmissionRejected`.

`BrokerGatedUIDriver` injects a one-shot `broker_request` callback and binds the existing B1 five-field envelope to the exact UTF-8 body SHA-256. It requests `admit` and then `begin_click` only inside the final pre-click callback. Both exact broker states must be returned. Any exception/ambiguous response propagates as uncertain, never as an authorized retry. `wake_adapter.wake_once` remains the source of durable UI-ledger transitions and must not automatically retry a possibly clicked attempt.

The injected callback is **not** authenticated by this module. For a real deployment it must use Ronja's [dedicated-UID, connected-peer-verified B5 client](https://github.com/martintommerstigen/Baton/blob/research/ronja-remote-security-r5-tls-2026-11-10/remote_security/broker_peer.py) or an equivalent independently verified adapter. B1's current `wake_admission_broker.query` is not safe as a production client: it transmits before authenticating the server. B1's current same-UID 0600 broker socket is not yet compatible with Ronja's distinct-UID production boundary.

## Negative controls

`test_wake_broker_ui.py` uses isolated SQLite broker state and fake UI (no Greg, no CDP, no actual ChatGPT messages). It checks exact envelope/order, preflight rejection without broker admission, pause before admission, wrong broker response, crash immediately after committed `begin_click` before click, crash after click before observation, pause after begin, composer mutation after begin, and invalid callback. The two crash cases restart the broker store and prove the old attempt cannot be re-admitted. The test harness's callback is deliberately local and **does not** attest server identity.

## Unclosed boundaries / next falsifiers

1. **Not integrated into the live CLI:** `run_chatgpt_wake.py` and `run_chatgpt_wake_chain.py` still instantiate the legacy direct driver. The new adapter must **not** be used live until a cross-UID authenticated broker client, actual source-turn attestation, and authorization policy are available. Do not silently enable it.
2. A broker can commit `begin_click` while the UI later refuses to click. The state remains `uncertain`, not a false delivery receipt. No automatic retry. Reconciliation must be read-only.
3. A pause committed after the final UI pause check can still race the click. The callback and recheck reduce the interval, **not** establish an atomic pause/click boundary. A trusted executor with an enforced exclusive capability is still needed.
4. A same-UID process may bypass the broker and click independently; `SO_PEERCRED` proves UID, not a ChatGPT source turn. A forged B→C request remains a known negative control.
5. DOM selectors and turn IDs remain unverified on Greg. Need three preexisting allowlisted conversation URLs, a unique independently observed A request, B reply with unique assistant turn ID and exact `BATON_NEXT`, then C reply. Preserve `PAUSE_UI_WRITES` and do not perform any send while it is active.
6. GitHub CI is an offline simulated result, not `tested-live`. The Remote Desktop Commander monthly quota rejected read-only Greg access. No Greg installation or browser send was attempted.

**Classification:** implemented / offline tests pending CI at documentation time. B1/B5 remains open; do not merge to production or call `done`.
