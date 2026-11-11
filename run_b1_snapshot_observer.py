"""B1 existing-chat source observer: R24-scoped OS preflight, then R23/R22.

No browser/CDP object, UI Send, shell or general remote command. A successful
preflight is a point-in-time boundary observation, never ChatGPT authorship,
permission to click, or proof of A->B->C. Run as an isolated non-root UID.
"""
import argparse
import json
import os

from b1_snapshot_relay import observe_via_snapshots
from chatgpt_ui_driver import PAUSE_FILE, pause_active

REQUIRED_CHECKS = frozenset({
    "distinct_uid", "no_inherited_sockets", "profile_open_denied",
    "declared_loopback_cdp_unreachable", "snapshot_peer_uid",
})
NETWORK_CHECKS = frozenset({"different_netns", "tcp_socket_families_denied"})


def enforce_scoped_boundary(*, collector_pid, collector_uid, profile,
                            snapshot_socket, cdp_host, cdp_port, auditor=None):
    """Reuse Ronja R24 unchanged. Missing dependency/ambiguous result = deny.

    This is a *scoped preflight*, NOT a security attestation or admission.
    """
    if auditor is None:
        from remote_security.observer_boundary import audit_observer_boundary
        auditor = audit_observer_boundary
    result = auditor(collector_pid=collector_pid, collector_uid=collector_uid,
                     profile=profile, snapshot_socket=snapshot_socket,
                     cdp_host=cdp_host, cdp_port=cdp_port)
    if (type(result) is not dict
            or result.get("status") != "scoped_preflight_pass_not_attestation"
            or type(result.get("checks")) is not list
            or any(type(item) is not str for item in result["checks"])
            or len(set(result["checks"])) != len(result["checks"])):
        raise PermissionError("R24 scoped boundary not established")
    checks = frozenset(result["checks"])
    if not REQUIRED_CHECKS.issubset(checks) or not (checks & NETWORK_CHECKS):
        raise PermissionError("R24 required isolation check missing")
    return result


def guarded_query(query, preflight, pause_checker):
    """Recheck OS boundary immediately before each snapshot/witness request.

    A boundary failure after a possible witness commit is handled by the
    caller as uncertain; this function never retries.
    """
    if not all(callable(fn) for fn in (query, preflight, pause_checker)):
        raise TypeError("query, boundary and pause callbacks required")

    def send(req):
        if pause_checker() is not False:
            raise PermissionError("PAUSE_UI_WRITES active or untrusted")
        preflight()
        if pause_checker() is not False:
            raise PermissionError("pause changed during OS boundary preflight")
        return query(req)
    return send


def require_lifetime_guard(installer=None):
    """Install Ronja R25's persistent kernel policy before ANY B1 observation.

    R24 is a point-in-time check. Without R25, a direct invocation of this
    module would silently bypass the lifetime restriction. A missing R25
    dependency, failed kernel installation or wrong receipt must fail closed.
    This receipt is not a host attestation or ChatGPT authorship evidence.
    """
    if installer is None:
        try:
            from remote_security.observer_lifetime_guard import install_observer_lifetime_guard
        except ImportError as exc:
            raise PermissionError("R25 lifetime guard unavailable") from exc
        installer = install_observer_lifetime_guard
    if not callable(installer):
        raise TypeError("R25 installer must be callable")
    receipt = installer()
    if type(receipt) is not str or receipt != "lifetime_guard_loaded_not_host_attestation":
        raise PermissionError("R25 kernel lifetime restriction not established")
    return receipt

def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    for arg in ("source", "source-turn-id", "target", "id", "payload-sha256",
                "snapshot-socket", "collector-uid", "collector-pid",
                "browser-profile", "broker-socket", "broker-uid"):
        p.add_argument("--" + arg, required=True)
    p.add_argument("--cdp-host", default="127.0.0.1",
                   choices=("127.0.0.1", "::1"))
    p.add_argument("--cdp-port", type=int, default=9222)
    a = p.parse_args(argv)
    try:
        collector_uid, broker_uid, collector_pid = (
            int(a.collector_uid), int(a.broker_uid), int(a.collector_pid))
    except ValueError:
        p.error("peer UIDs and collector PID must be integers")
    if (min(collector_uid, broker_uid) <= 0 or collector_pid <= 1
            or collector_uid == broker_uid
            or os.geteuid() in (0, collector_uid, broker_uid)):
        p.error("observer, collector and broker must use distinct non-root UIDs")

    # A direct B1 entry point must never bypass Ronja R25's persistent guard.
    require_lifetime_guard()

    from remote_security.broker_peer import query_verified_broker
    pause_checker = lambda: pause_active(PAUSE_FILE)

    def preflight():
        return enforce_scoped_boundary(
            collector_pid=collector_pid, collector_uid=collector_uid,
            profile=a.browser_profile, snapshot_socket=a.snapshot_socket,
            cdp_host=a.cdp_host, cdp_port=a.cdp_port)

    # Do not even begin a snapshot if R24 cannot inspect the declared boundary.
    if pause_checker() is not False:
        raise PermissionError("PAUSE_UI_WRITES active or untrusted")
    preflight()

    def snapshot_query(req):
        return query_verified_broker(a.snapshot_socket, collector_uid, req,
                                     require_distinct_uid=True)

    def witness_query(req):
        return query_verified_broker(a.broker_socket, broker_uid, req,
                                     require_distinct_uid=True)

    result = observe_via_snapshots(
        source=a.source, source_turn_id=a.source_turn_id,
        target=a.target, message_id=a.id, payload_sha256=a.payload_sha256,
        snapshot_query=guarded_query(snapshot_query, preflight, pause_checker),
        witness_query=guarded_query(witness_query, preflight, pause_checker),
        pause_checker=pause_checker)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
