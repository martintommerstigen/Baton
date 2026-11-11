"""B1/B5 H26: opt-in, source-only R24/R25/R27 four-session observer.

This does not send to ChatGPT, authenticate ChatGPT authorship, or verify
A->B->C. Run only as a dedicated, non-root observer UID. No shell or CDP.
R24 is a preconnection snapshot; R25/R27 are persistent kernel restrictions.
"""
from __future__ import annotations

import argparse
import json
import os
import socket

from b1_snapshot_relay import observe_via_snapshots, snapshot_request
from chatgpt_ui_driver import PAUSE_FILE, pause_active
from run_b1_snapshot_observer import (
    enforce_scoped_boundary, REQUIRED_CHECKS, NETWORK_CHECKS)

EXPECTED_GUARD = "lifetime_guard_loaded_not_host_attestation"
EXPECTED_SEAL = "four_role_pinned_sessions_sealed_not_host_attestation"


def run_sealed_observation(*, source, source_turn_id, target, message_id,
                           payload_sha256, snapshot_socket, broker_socket,
                           collector_uid, broker_uid, pause_checker, preflight,
                           install_guard, check_endpoint, sealer,
                           observer=observe_via_snapshots):
    """One irreversible observation attempt; never retry a possible witness.

    Dependencies are injected only to exercise the same orchestration in
    isolated tests. The CLI below binds every dependency to its pinned module.
    """
    req = snapshot_request(source, source_turn_id, target, message_id,
                           payload_sha256)
    if (type(collector_uid) is not int or type(broker_uid) is not int
            or min(collector_uid, broker_uid) <= 0
            or len({os.geteuid(), collector_uid, broker_uid}) != 3
            or os.geteuid() == 0 or os.getuid() != os.geteuid()):
        raise PermissionError("distinct non-root observer, collector and broker required")
    if not all(callable(x) for x in (pause_checker, preflight, install_guard,
                                    check_endpoint, sealer, observer)):
        raise TypeError("trusted observation dependencies required")
    if pause_checker() is not False:
        raise PermissionError("PAUSE_UI_WRITES active or unknown")
    if install_guard() != EXPECTED_GUARD:
        raise PermissionError("R25 lifetime kernel guard unavailable")
    if pause_checker() is not False:
        raise PermissionError("pause changed before R24 preflight")
    boundary = preflight()
    if (type(boundary) is not dict
            or boundary.get("status") != "scoped_preflight_pass_not_attestation"
            or type(boundary.get("checks")) is not list
            or any(type(c) is not str for c in boundary["checks"])
            or len(set(boundary["checks"])) != len(boundary["checks"])
            or not REQUIRED_CHECKS.issubset(boundary["checks"])
            or not NETWORK_CHECKS.intersection(boundary["checks"])):
        raise PermissionError("R24 boundary not established")
    if pause_checker() is not False:
        raise PermissionError("pause changed after R24 preflight")

    # Validate endpoint paths before opening any connection.
    # R27 rechecks pathname, inode, peer UID and socket inventory after connect.
    check_endpoint(snapshot_socket, collector_uid)
    check_endpoint(broker_socket, broker_uid)
    streams = []
    try:
        for endpoint in (snapshot_socket,) * 3 + (broker_socket,):
            if pause_checker() is not False:
                raise PermissionError("pause changed during preconnection")
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            streams.append(sock)
            sock.settimeout(3)
            sock.connect(endpoint)
        if pause_checker() is not False:
            raise PermissionError("pause changed before irreversible R27 seal")
        sealed = sealer(tuple(streams[:3]), streams[3],
                        snapshot_endpoint=snapshot_socket,
                        witness_endpoint=broker_socket,
                        collector_uid=collector_uid, broker_uid=broker_uid,
                        approved_snapshot=req, pause_checker=pause_checker)
        if getattr(sealed, "receipt", None) != EXPECTED_SEAL:
            raise PermissionError("R27 seal receipt invalid")
        # R27 owns four one-use streams and their strict stage ordering.
        # B1 owns two checks, durable R22 witness and post-witness recheck.
        return observer(source=source, source_turn_id=source_turn_id,
                        target=target, message_id=message_id,
                        payload_sha256=payload_sha256,
                        snapshot_query=sealed.snapshot_query,
                        witness_query=sealed.witness_query,
                        pause_checker=pause_checker)
    finally:
        for sock in streams:
            sock.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--opt-in-source-observation", action="store_true", required=True)
    for name in ("source", "source-turn-id", "target", "id", "payload-sha256",
                 "snapshot-socket", "collector-uid", "collector-pid",
                 "browser-profile", "broker-socket", "broker-uid"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--cdp-host", choices=("127.0.0.1", "::1"), default="127.0.0.1")
    parser.add_argument("--cdp-port", type=int, default=9222)
    args = parser.parse_args(argv)
    try:
        collector_uid = int(args.collector_uid)
        broker_uid = int(args.broker_uid)
        collector_pid = int(args.collector_pid)
    except ValueError:
        parser.error("UID and PID must be integers")
    if collector_pid <= 1:
        parser.error("collector PID must identify a running process")
    # Imports fail closed if Ronja's exact R25/R26/R27 modules are absent.
    from remote_security.observer_lifetime_guard import install_observer_lifetime_guard
    from remote_security.sealed_unix_channel import _check_path
    from remote_security.sealed_observer_sessions import seal_observer_sessions

    def preflight():
        return enforce_scoped_boundary(
            collector_pid=collector_pid, collector_uid=collector_uid,
            profile=args.browser_profile, snapshot_socket=args.snapshot_socket,
            cdp_host=args.cdp_host, cdp_port=args.cdp_port)

    try:
        result = run_sealed_observation(
            source=args.source, source_turn_id=args.source_turn_id,
            target=args.target, message_id=args.id,
            payload_sha256=args.payload_sha256,
            snapshot_socket=args.snapshot_socket, broker_socket=args.broker_socket,
            collector_uid=collector_uid, broker_uid=broker_uid,
            pause_checker=lambda: pause_active(PAUSE_FILE),
            preflight=preflight, install_guard=install_observer_lifetime_guard,
            check_endpoint=_check_path, sealer=seal_observer_sessions)
    except (PermissionError, ValueError, TypeError, OSError, RuntimeError,
            ImportError) as exc:
        # No raw message, tokens, browser profile, or full exception trace.
        uncertain = "Uncertain" in type(exc).__name__
        print(json.dumps({"state": "uncertain_no_retry" if uncertain else "blocked",
                          "classification": "source_only_not_chat_wake"}))
        return 3 if uncertain else 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
