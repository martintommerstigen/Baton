"""B1 opt-in, fail-closed single-hop existing-chat wake using Ronja's B5 peer gate.

The existing A assistant turn must be exactly\nBATON_WAKE <target-UUID> <message-id> sha256:<approved-body-UTF8-SHA256>.\nThe verified live CLI refuses legacy target-only commands.\n\nRequires the B5 remote_security.broker_peer module on PYTHONPATH, a broker
running under a different unprivileged Linux UID, and two already-open
authorized ChatGPT tabs. No browser launch, cookie access or blind retry.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import time

from chatgpt_ui_driver import ChatGPTUIDriver, conversation_id, pause_active, PAUSE_FILE
from run_chatgpt_wake import local_cdp
from wake_adapter import wake_once
from wake_broker_ui import BrokerGatedUIDriver
from wake_contract import WakeLedger
from wake_origin import verify_source_turn, guarded_source_broker_request
from wake_ui_lock import LockingUIDriver


def make_verified_broker_request(socket_path, expected_uid, *, timeout=3.0):
    """Require B5's connected-peer check; never fall back to B1's unsafe query()."""
    if type(expected_uid) is not int or expected_uid <= 0 or expected_uid == os.getuid():
        raise ValueError("Broker must use a dedicated non-root UID distinct from UI worker")
    if type(socket_path) is not str or not socket_path.startswith('/'):
        raise ValueError("Absolute broker socket path required")
    try:
        from remote_security.broker_peer import query_verified_broker
    except ImportError as exc:
        raise RuntimeError("B5 verified peer client not installed; no UI writes") from exc

    def request(envelope):
        if type(envelope) is not dict or envelope.get('op') not in ('admit', 'begin_click'):
            raise ValueError("Only admission and begin_click are permitted")
        return query_verified_broker(socket_path, expected_uid, envelope,
                                     timeout=timeout, require_distinct_uid=True)
    return request


def select_existing_tabs(browser, source, target):
    if source == target:
        raise ValueError("Source and target must be different existing conversations")
    found = {source: [], target: []}
    for context in browser.contexts:
        for page in context.pages:
            try:
                cid = conversation_id(page.url)
            except ValueError:
                continue
            if cid in found:
                found[cid].append(page)
    if any(len(pages) != 1 for pages in found.values()):
        raise RuntimeError("Require exactly one already-open source and target tab")
    return {cid: pages[0] for cid, pages in found.items()}


class WaitForReply:
    def __init__(self, driver, wait_seconds):
        self.driver = driver
        self.wait_seconds = wait_seconds

    def submit_once(self, *args):
        return self.driver.submit_once(*args)

    def observe_reply(self, conversation_id, message_id, expected_digest):
        deadline = time.monotonic() + self.wait_seconds
        while True:
            result = self.driver.observe_reply(conversation_id, message_id, expected_digest)
            if result is not None:
                return result
            if time.monotonic() >= deadline:
                return None
            time.sleep(1)


def execute_once(ledger, source_driver, target_driver, source, target,
                 source_turn_id, message_id, body, broker_request, wait_seconds,
                 *, require_payload_authority=False):
    """Verify source assistant turn before any durable admission or UI write."""
    if source == target:
        raise ValueError("Distinct source/target conversations required")
    if type(body) is not str or not body.strip():
        raise ValueError("Nonempty approved body required")
    if not 0 <= wait_seconds <= 600:
        raise ValueError("Invalid observation window")
    digest = hashlib.sha256(body.encode('utf-8')).hexdigest()
    commitment = digest if require_payload_authority else None
    verify_source_turn(source_driver, source, source_turn_id, target, message_id,
                       commitment)
    guarded_request = guarded_source_broker_request(
        source_driver, source, source_turn_id, target, message_id,
        broker_request, expected_digest=commitment)
    gated = BrokerGatedUIDriver(target_driver, guarded_request, source, source_turn_id)
    return wake_once(ledger, WaitForReply(gated, wait_seconds), message_id,
                     source, target, digest, body, source_turn_id)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'target', 'source-turn-id', 'id', 'body', 'db',
                 'broker-socket', 'broker-uid'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--cdp', default='http://127.0.0.1:9222')
    parser.add_argument('--wait-seconds', type=int, default=120)
    args = parser.parse_args(argv)
    local_cdp(args.cdp)
    if pause_active(PAUSE_FILE):
        raise RuntimeError("UI writes paused or pause path untrusted")
    if not 0 <= args.wait_seconds <= 600:
        parser.error("Invalid observation window")
    try:
        broker_uid = int(args.broker_uid)
    except ValueError:
        parser.error("Invalid broker UID")
    broker_request = make_verified_broker_request(args.broker_socket, broker_uid)
    from playwright.sync_api import sync_playwright
    # Lock only the actual UI submission, never the subsequent reply wait.
    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(args.cdp)
        tabs = select_existing_tabs(browser, args.source, args.target)
        source_driver = ChatGPTUIDriver(tabs[args.source], frozenset({args.source}))
        target_driver = LockingUIDriver(ChatGPTUIDriver(tabs[args.target], frozenset({args.target})))
        ledger = WakeLedger(args.db)
        result = execute_once(ledger, source_driver, target_driver, args.source,
                              args.target, args.source_turn_id, args.id, args.body,
                              broker_request, args.wait_seconds,
                              require_payload_authority=True)
        print(json.dumps({'source': args.source, 'target': args.target,
                          'message_id': args.id, 'source_turn_id': args.source_turn_id,
                          'state': result, 'status': 'not_a_chain_completion'}))


if __name__ == '__main__':
    main()
