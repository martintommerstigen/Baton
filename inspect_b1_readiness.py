"""B1/B5 read-only readiness inspection for three *existing* ChatGPT tabs.

The live CLI requires A's exact target, message ID and SHA-256 body commitment.
This program NEVER sends a message, creates a chat, starts a browser, or
authorizes a wake. A successful preflight is NOT delivery, receipt, or I.
Only connect to an already-running loopback CDP endpoint and a separately
authenticated B5 broker using a single read-only "status" request.
"""
import argparse
import hashlib
import json
import os
import re

from chatgpt_ui_driver import CHAT_ID, ChatGPTUIDriver, PAUSE_FILE, conversation_id, marker_for, pause_active
from wake_origin import source_requested_wake

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def inspect_boundary(browser, *, a, b, c, source_turn_id, first_id,
                     payload_sha256, pause_checker, broker_probe,
                     driver_factory=ChatGPTUIDriver,
                     require_payload_authority=False):
    """Return a sanitized report; never call a UI write method.

    A's existing assistant command authorizes the B target and first message
    ID ONLY. The operator-supplied payload digest is not A's content approval.
    A successful result is a *read-only preflight*, not a send capability.
    """
    if (len({a, b, c}) != 3 or any(type(cid) is not str or not CHAT_ID.fullmatch(cid)
                                   for cid in (a, b, c))):
        raise ValueError("three distinct existing conversation UUIDs required")
    marker_for(first_id)
    if type(source_turn_id) is not str or not source_turn_id.strip():
        raise ValueError("nonempty A assistant turn ID required")
    if type(payload_sha256) is not str or not _SHA256.fullmatch(payload_sha256):
        raise ValueError("lowercase SHA-256 of operator-approved body required")
    if not callable(pause_checker) or not callable(broker_probe):
        raise TypeError("read-only pause and authenticated broker probes required")

    report = {
        "status": "blocked",
        "classification": "read_only_preflight_not_existing_chat_wake",
        "conversation_ids": {"a": a, "b": b, "c": c},
        "matching_existing_tabs": {"a": 0, "b": 0, "c": 0},
        "pause": "active_or_untrusted",
        "broker": "unavailable_or_untrusted",
        "broker_outstanding": None,
        "source_turn_sha256": None,
        "source_command": "not_verified",
        "source_authorizes_exact_payload": False,
        "payload_sha256": payload_sha256,
        "payload_provenance": "operator_supplied_not_source_committed",
        "reasons": [],
    }
    try:
        paused = pause_checker()
        if type(paused) is not bool or paused:
            report["reasons"].append("pause_active_or_untrusted")
        else:
            report["pause"] = "clear"
    except Exception:
        report["reasons"].append("pause_check_failed")

    try:
        # No 'admit', 'begin_click', or any mutating broker request.
        state = broker_probe()
        if (type(state) is dict and state.get("state") == "ready"
                and type(state.get("outstanding")) is int
                and state["outstanding"] == 0):
            report["broker"] = "ready_no_outstanding"
            report["broker_outstanding"] = 0
        else:
            report["reasons"].append("broker_not_ready_or_untrusted")
            if type(state) is dict and type(state.get("outstanding")) is int:
                report["broker_outstanding"] = state["outstanding"]
    except Exception:
        report["reasons"].append("broker_probe_failed")

    found = {a: [], b: [], c: []}
    try:
        for context in browser.contexts:
            for page in context.pages:
                try:
                    cid = conversation_id(page.url)
                except (ValueError, AttributeError, TypeError):
                    continue
                if cid in found:
                    found[cid].append(page)
    except Exception:
        report["reasons"].append("browser_enumeration_failed")
        return report
    report["matching_existing_tabs"] = {
        "a": len(found[a]), "b": len(found[b]), "c": len(found[c])
    }
    if any(len(found[cid]) != 1 for cid in (a, b, c)):
        report["reasons"].append("missing_or_duplicate_existing_tab")
        return report

    try:
        source = driver_factory(found[a][0], frozenset({a}))
        if source.is_generating(a):
            report["reasons"].append("source_still_generating")
        else:
            text = source.read_assistant_turn(a, source_turn_id)
            if type(text) is not str:
                report["reasons"].append("source_turn_unreadable")
            else:
                report["source_turn_sha256"] = hashlib.sha256(text.encode("utf-8")).hexdigest()
                if source_requested_wake(text, b, first_id, payload_sha256):
                    report["source_command"] = "exact_target_message_id_and_payload_digest"
                    report["source_authorizes_exact_payload"] = True
                    report["payload_provenance"] = "source_turn_committed_digest_operator_supplied_body"
                elif not require_payload_authority and source_requested_wake(text, b, first_id):
                    report["source_command"] = "exact_target_and_message_id"
                else:
                    report["reasons"].append("source_command_mismatch")
    except Exception:
        report["reasons"].append("source_turn_unavailable_or_ambiguous")

    for cid, role in ((b, "b"), (c, "c")):
        try:
            driver = driver_factory(found[cid][0], frozenset({cid}))
            if driver.is_generating(cid):
                report["reasons"].append(role + "_still_generating")
        except Exception:
            report["reasons"].append(role + "_read_only_ui_check_failed")

    if (not report["reasons"] and report["pause"] == "clear"
            and report["broker"] == "ready_no_outstanding"
            and (report["source_authorizes_exact_payload"]
                 if require_payload_authority else report["source_command"] != "not_verified")):
        report["status"] = "preflight_passed_not_delivery"
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ("a", "b", "c", "source-turn-id", "first-id",
                  "payload-sha256", "broker-socket", "broker-uid"):
        parser.add_argument("--" + field, required=True)
    parser.add_argument("--cdp", default="http://127.0.0.1:9222")
    args = parser.parse_args(argv)
    from run_chatgpt_wake import local_cdp
    local_cdp(args.cdp)
    try:
        uid = int(args.broker_uid)
    except ValueError:
        parser.error("broker UID must be an integer")
    if uid <= 0 or uid == os.getuid():
        parser.error("broker must run as a distinct, non-root UID")
    if not args.broker_socket.startswith("/"):
        parser.error("broker socket path must be absolute")

    # A missing B5 peer verifier is a hard failure; no unsafe query fallback.
    from remote_security.broker_peer import query_verified_broker
    from playwright.sync_api import sync_playwright

    def broker_status():
        return query_verified_broker(
            args.broker_socket, uid, {"op": "status"},
            timeout=3.0, require_distinct_uid=True
        )

    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(args.cdp)
        report = inspect_boundary(
            browser, a=args.a, b=args.b, c=args.c,
            source_turn_id=args.source_turn_id, first_id=args.first_id,
            payload_sha256=args.payload_sha256,
            pause_checker=lambda: pause_active(PAUSE_FILE),
            broker_probe=broker_status,
            require_payload_authority=True,
        )
    print(json.dumps(report, sort_keys=True))
    return 0 if report["status"] == "preflight_passed_not_delivery" else 2


if __name__ == "__main__":
    raise SystemExit(main())
