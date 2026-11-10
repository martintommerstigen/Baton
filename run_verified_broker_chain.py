"""Opt-in B1/B5 A->B->C runner for three *existing* ChatGPT tabs.

No browser creation/login, no implicit retry, no arbitrary model-authored payload.
A must emit BATON_WAKE B FIRST_ID. The observed assistant turn in B must
be the *exact* BATON_NEXT C. B's source turn is the durable receipt for A->B.
Every UI click requires Ronja's connected-peer-verified B5 admission.
Not a live-verification claim: only a real Greg/browser run can establish that.
"""
from __future__ import annotations

import argparse
import hashlib
import json

from chatgpt_ui_driver import (
    CHAT_ID, ChatGPTUIDriver, PAUSE_FILE, marker_for, pause_active,
)
from run_chatgpt_wake import local_cdp
from run_chatgpt_wake_chain import select_pages
from run_verified_broker_wake import (
    WaitForReply, execute_once, make_verified_broker_request,
)
from wake_adapter import wake_once
from wake_broker_ui import BrokerGatedUIDriver
from wake_chain import next_target_from_reply
from wake_contract import WakeLedger
from wake_ui_lock import ui_controller_lock
from wake_turn_snapshot import (
    CapturingTarget, SourceEvidenceChanged, TurnSnapshotStore,
    guarded_second_hop, verify_current_b_turn,
)


def _receipt(ledger, message_id):
    row = ledger.provenance(message_id)
    if row is None:
        return None
    source, target, source_turn, digest, state, observed_turn, updated = row
    return {
        "message_id": message_id,
        "source_chat": source,
        "target_chat": target,
        "source_turn_id": source_turn,
        "target_assistant_turn_id": observed_turn,
        "payload_sha256": digest,
        "state": state,
        "updated_unix": updated,
    }


def run_verified_chain(ledger, driver_a, driver_b, driver_c, *,
                       a, b, c, source_turn_id, first_id, second_id,
                       first_body, second_body, broker_request,
                       wait_seconds=120):
    """Two-hop chain; a verified first-hop B turn is required before C.

    The broker client is an injected *authenticated* callback. Callers must
    construct it with make_verified_broker_request, never unauthenticated query.
    Offline tests inject a fake callback and do not establish peer identity.
    """
    if len({a, b, c}) != 3 or any(
        not isinstance(cid, str) or not CHAT_ID.fullmatch(cid)
        for cid in (a, b, c)
    ):
        raise ValueError("Three distinct existing conversation UUIDs required")
    marker_for(first_id)
    marker_for(second_id)
    if first_id == second_id:
        raise ValueError("Distinct message IDs required")
    if not isinstance(source_turn_id, str) or not source_turn_id.strip():
        raise ValueError("A assistant source-turn ID required")
    if any(not isinstance(body, str) or not body.strip()
           for body in (first_body, second_body)):
        raise ValueError("Both preapproved bodies must be nonempty")
    if not callable(broker_request):
        raise TypeError("Verified broker request callback required")
    if not isinstance(wait_seconds, (int, float)) or not 0 <= wait_seconds <= 600:
        raise ValueError("Invalid observation window")

    snapshots = TurnSnapshotStore(ledger)
    first = execute_once(
        ledger, driver_a, CapturingTarget(driver_b, snapshots, first_id), a, b, source_turn_id,
        first_id, first_body, broker_request, wait_seconds,
    )
    outcome = {
        "a_to_b": first,
        "b_to_c": "not_attempted",
        "a_to_b_receipt": _receipt(ledger, first_id),
        "b_to_c_receipt": _receipt(ledger, second_id),
        "status": "not_live_proof_without_real_browser_observation",
    }
    if first != "verified":
        return outcome

    # The receipt is the only authorized B source-turn identifier. A queued
    # transport message or unverified/fabricated B command is insufficient.
    b_turn_id = ledger.state(first_id)[2]
    if not b_turn_id:
        raise RuntimeError("Verified B assistant turn ID missing")
    # B's first observed text must survive unchanged at the same DOM turn ID.
    # A later command inserted into the same ID is not source authorization.
    try:
        snap = verify_current_b_turn(ledger, snapshots, driver_b, first_id, b, c)
    except (SourceEvidenceChanged, ValueError, RuntimeError):
        outcome["b_to_c"] = "not_authorized"
        return outcome
    outcome["b_source_snapshot"] = {
        "chat": snap.chat, "turn_id": snap.turn_id,
        "text_sha256": snap.text_sha256, "extractor": snap.extractor,
        "source_url": snap.source_url, "observed_utc": snap.observed_utc,
    }

    # The C payload was preauthorized. Recheck B before and after both
    # broker operations. After begin_click, failure stays uncertain.
    guarded_request = guarded_second_hop(
        broker_request, ledger, snapshots, driver_b, first_id, b, c,
    )
    gated_c = BrokerGatedUIDriver(driver_c, guarded_request, b, b_turn_id)
    digest_c = hashlib.sha256(second_body.encode("utf-8")).hexdigest()
    second = wake_once(
        ledger, WaitForReply(gated_c, wait_seconds),
        second_id, b, c, digest_c, second_body, b_turn_id,
    )
    outcome["b_to_c"] = second
    outcome["b_to_c_receipt"] = _receipt(ledger, second_id)
    return outcome


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in (
        "a", "b", "c", "source-turn-id", "first-id", "second-id",
        "first-body", "second-body", "db", "broker-socket", "broker-uid",
    ):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--cdp", default="http://127.0.0.1:9222")
    parser.add_argument("--wait-seconds", type=int, default=120)
    args = parser.parse_args(argv)

    # Authenticate the peer-client interface and check the local pause
    # *before* opening any browser session. The UI driver rechecks before Send.
    if pause_active(PAUSE_FILE):
        raise RuntimeError("UI writes paused or pause path untrusted")
    local_cdp(args.cdp)
    try:
        uid = int(args.broker_uid)
    except ValueError:
        parser.error("Invalid broker UID")
    broker_request = make_verified_broker_request(args.broker_socket, uid)
    if not 0 <= args.wait_seconds <= 600:
        parser.error("Invalid wait window")

    from playwright.sync_api import sync_playwright

    with ui_controller_lock(), sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(args.cdp)
        pages = select_pages(browser, (args.a, args.b, args.c))
        drivers = {
            cid: ChatGPTUIDriver(page, frozenset({cid}))
            for cid, page in pages.items()
        }
        ledger = WakeLedger(args.db)
        result = run_verified_chain(
            ledger, drivers[args.a], drivers[args.b], drivers[args.c],
            a=args.a, b=args.b, c=args.c,
            source_turn_id=args.source_turn_id,
            first_id=args.first_id, second_id=args.second_id,
            first_body=args.first_body, second_body=args.second_body,
            broker_request=broker_request, wait_seconds=args.wait_seconds,
        )
        print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
