"""B1 H21: read-only existing-ChatGPT source-turn observer for Ronja R22.

This is a separate *local process role*, not a ChatGPT sender UID. It only
observes one already-open source tab and records a single-use observation claim
through a separately authenticated AF_UNIX broker. It NEVER clicks Send.
A successful claim is neither ChatGPT authorship nor an A->B wake.
"""
import argparse
import hashlib
import json
import os
import re

from chatgpt_ui_driver import (CHAT_ID, ChatGPTUIDriver, PAUSE_FILE,
                               conversation_id, marker_for, pause_active)
from run_chatgpt_wake import local_cdp
from wake_origin import verify_source_turn

_DIGEST = re.compile(r"^[0-9a-f]{64}$")


class ObservationOutcomeUncertain(RuntimeError):
    """A broker may have committed a witness. Do not retry automatically."""


def select_existing_source(browser, source):
    """No browser navigation; require exactly one existing source tab."""
    found = []
    for context in browser.contexts:
        for page in context.pages:
            try:
                cid = conversation_id(page.url)
            except (ValueError, AttributeError, TypeError):
                continue
            if cid == source:
                found.append(page)
    if len(found) != 1:
        raise RuntimeError("source tab missing or duplicated")
    return found[0]


def observe_once(driver, source, source_turn_id, target, message_id,
                 payload_sha256, broker_request, pause_checker):
    """Verify exact DOM command on both sides of one observe_source request.

    A returned success means only a durable *observation claim*. Even a real
    local observer can fabricate a DOM-reading result. The B1 controller must
    independently verify the source again before UI admission and click.
    """
    if (type(source) is not str or type(target) is not str
            or not CHAT_ID.fullmatch(source) or not CHAT_ID.fullmatch(target)
            or source == target):
        raise ValueError("two distinct existing ChatGPT UUIDs required")
    marker_for(message_id)
    if type(source_turn_id) is not str or not source_turn_id.strip():
        raise ValueError("nonempty source assistant turn ID required")
    if type(payload_sha256) is not str or not _DIGEST.fullmatch(payload_sha256):
        raise ValueError("lowercase approved UTF-8 body SHA-256 required")
    if not callable(broker_request) or not callable(pause_checker):
        raise TypeError("verified broker and pause callbacks required")

    def recheck():
        if pause_checker() is not False:
            raise PermissionError("PAUSE_UI_WRITES active or untrusted")
        # The source driver must be bound to this exact, existing URL.
        if conversation_id(driver.page.url) != source:
            raise PermissionError("source page changed")
        verify_source_turn(driver, source, source_turn_id, target,
                           message_id, payload_sha256)

    recheck()
    command = f"BATON_WAKE {target} {message_id} sha256:{payload_sha256}"
    req = {"op": "observe_source", "sender_id": source,
           "origin_turn_id": source_turn_id, "conversation_id": target,
           "message_id": message_id, "payload_sha256": payload_sha256,
           "source_command": command}
    # Final read before request; never observe a quoted/example command.
    recheck()
    try:
        result = broker_request(req)
    except Exception as exc:
        raise ObservationOutcomeUncertain(
            "broker observation outcome unknown; no automatic retry") from exc
    try:
        recheck()
    except Exception as exc:
        raise ObservationOutcomeUncertain(
            "source changed after possible witness commit; no retry") from exc
    if result != {"state": "source_observation_recorded_not_authorship"}:
        raise ObservationOutcomeUncertain(
            "witness not confirmed; do not retry without reconciliation")
    return {"state": "source_observation_recorded_not_authorship",
            "source_turn_sha256": hashlib.sha256(command.encode("utf-8")).hexdigest(),
            "classification": "local_observation_claim_not_chatgpt_authorship"}


def make_observer_broker_request(socket_path, broker_uid, timeout=3.0):
    """Authenticate broker peer *before* sending observation bytes."""
    if (type(broker_uid) is not int or broker_uid <= 0
            or broker_uid == os.geteuid()):
        raise ValueError("dedicated non-root broker UID required")
    if type(socket_path) is not str or not socket_path.startswith("/"):
        raise ValueError("absolute broker Unix-socket path required")
    try:
        from remote_security.broker_peer import query_verified_broker
    except ImportError as exc:
        raise RuntimeError("B5 authenticated broker client absent") from exc

    def request(req):
        if type(req) is not dict or req.get("op") != "observe_source":
            raise PermissionError("observer may only register a source claim")
        return query_verified_broker(socket_path, broker_uid, req,
                                     timeout=timeout, require_distinct_uid=True)
    return request


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ("source", "source-turn-id", "target", "id",
                  "payload-sha256", "broker-socket", "broker-uid"):
        parser.add_argument("--" + field, required=True)
    parser.add_argument("--cdp", default="http://127.0.0.1:9222")
    args = parser.parse_args(argv)
    local_cdp(args.cdp)
    if pause_active(PAUSE_FILE):
        raise RuntimeError("UI writes paused or pause path untrusted")
    try:
        uid = int(args.broker_uid)
    except ValueError:
        parser.error("invalid broker UID")
    request = make_observer_broker_request(args.broker_socket, uid)
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(args.cdp)
        page = select_existing_source(browser, args.source)
        driver = ChatGPTUIDriver(page, frozenset({args.source}))
        result = observe_once(driver, args.source, args.source_turn_id,
                              args.target, args.id, args.payload_sha256,
                              request, lambda: pause_active(PAUSE_FILE))
    print(json.dumps({"source": args.source, "target": args.target,
                      "message_id": args.id, "origin_turn_id": args.source_turn_id,
                      **result}, sort_keys=True))


if __name__ == "__main__":
    main()
