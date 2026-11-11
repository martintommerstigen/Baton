"""B5/B2 read-only source-broker readiness probe; no request, capture or UI.

A pathname check is *metadata*, not proof that a server is alive. An opt-in
AF_UNIX connection checks the kernel peer UID without sending request bytes;
that contact is observable by the service and is not a physical measurement.
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import stat
import struct

from remote_security.broker_peer import _checked_socket_path, UntrustedBroker


class ProbeUncertain(RuntimeError):
    """No verified service identity; never escalate or retry automatically."""


def probe(socket_path, expected_uid, *, connect=False, timeout=0.5):
    """Return a narrowly scoped, non-secret local endpoint observation.

    `connect=False` performs no socket connection and never sends bytes.
    `connect=True` performs exactly one AF_UNIX connection, checks SO_PEERCRED,
    sends zero application bytes and then closes. The service may observe the
    connection; this is O/contact, not an authenticated research job or wake.
    """
    if (os.geteuid() == 0 or os.getuid() != os.geteuid()
            or type(expected_uid) is not int or expected_uid <= 0
            or expected_uid == os.geteuid()):
        raise UntrustedBroker("dedicated different non-root service UID required")
    if type(connect) is not bool:
        raise ValueError("connect must be a boolean")
    if type(timeout) not in (int, float) or not 0 < timeout <= 2:
        raise ValueError("timeout must be within (0,2] seconds")
    if not hasattr(socket, "SO_PEERCRED") or not hasattr(socket, "AF_UNIX"):
        raise UntrustedBroker("Linux peer credentials required")
    try:
        path = _checked_socket_path(socket_path, expected_uid)
        before = path.lstat()
    except UntrustedBroker:
        raise
    except OSError as exc:
        raise ProbeUncertain("endpoint metadata unavailable; no retry") from exc
    if (not stat.S_ISSOCK(before.st_mode) or before.st_uid != expected_uid
            or before.st_mode & 0o777 != 0o660):
        raise UntrustedBroker("unexpected broker socket mode/owner")
    result = {
        "schema": "baton.source_probe.v1",
        "state": "endpoint_metadata_only",
        "peer_uid_verified": False,
        "request_bytes_sent": 0,
        "capture": "not_attempted",
        "chat_wake": "not_attempted",
        "greg_live": "not_established",
        "tcp_exposure": "not_checked",
    }
    if not connect:
        return result
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout)
            sock.connect(str(path))
            credentials = sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED,
                                           struct.calcsize("3i"))
            if len(credentials) != struct.calcsize("3i"):
                raise UntrustedBroker("missing peer credentials")
            pid, uid, gid = struct.unpack("3i", credentials)
            if pid <= 0 or uid != expected_uid or gid < 0:
                raise UntrustedBroker("connected peer UID mismatch")
            # Recheck every ancestor as well as the endpoint after connect.
            # A renamed directory or symlink substitution is not a stable path.
            _checked_socket_path(socket_path, expected_uid)
            after = path.lstat()
            if (not stat.S_ISSOCK(after.st_mode) or after.st_uid != expected_uid
                    or after.st_mode & 0o777 != 0o660
                    or (after.st_dev, after.st_ino) != (before.st_dev, before.st_ino)):
                raise UntrustedBroker("endpoint changed during probe")
            # No send, recv, or application protocol. close() sends EOF only.
            result["state"] = "kernel_peer_uid_verified_no_request"
            result["peer_uid_verified"] = True
            return result
    except (OSError, TimeoutError) as exc:
        raise ProbeUncertain("socket peer probe uncertain; no retry") from exc


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--socket", required=True)
    parser.add_argument("--service-uid", type=int, required=True)
    parser.add_argument("--connect-once", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = probe(args.socket, args.service_uid, connect=args.connect_once)
    except (UntrustedBroker, ProbeUncertain, ValueError) as exc:
        print(json.dumps({"state": "rejected_or_uncertain_no_retry",
                          "error_type": type(exc).__name__}, sort_keys=True))
        return 3
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
