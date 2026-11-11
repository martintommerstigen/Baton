"""B5/B2 fail-closed, scoped Linux observer isolation preflight.

Checks one declared collector PID, loopback CDP port, browser-profile directory
and snapshot AF_UNIX endpoint. This is NOT a proof of all browser capabilities,
ChatGPT authorship, a UI Send authorization, or a remote attestation.
No shell, browser API, application payload, credential, or filesystem write.
"""
from __future__ import annotations

import argparse
import errno
import json
import os
from pathlib import Path
import socket
import stat
import struct


class BoundaryDenied(PermissionError):
    """The observer isolation boundary is missing or cannot be established."""


def _canonical_path(value):
    if (type(value) is not str or not value.startswith('/') or '\x00' in value
            or any(p in ('', '.', '..') for p in value.split('/')[1:])):
        raise BoundaryDenied('absolute canonical path required')
    return value


def _netns(path):
    try:
        info = os.stat(path)
    except OSError as exc:
        raise BoundaryDenied('network namespace not inspectable') from exc
    return (info.st_dev, info.st_ino)


def _tcp_socket_families_denied():
    """Independent fallback when /proc/<other UID>/ns/net is not inspectable.

    This requires the OS to deny creation of BOTH TCP address families;
    mere ECONNREFUSED on a selected port is never sufficient.
    """
    for family in (socket.AF_INET, socket.AF_INET6):
        try:
            probe = socket.socket(family, socket.SOCK_STREAM)
        except OSError as exc:
            if exc.errno in (errno.EAFNOSUPPORT, errno.EPERM, errno.EACCES):
                continue
            raise BoundaryDenied('TCP address-family policy ambiguous') from exc
        else:
            probe.close()
            return False
    return True


def _network_guard(collector_pid):
    try:
        if _netns('/proc/self/ns/net') != _netns(f'/proc/{collector_pid}/ns/net'):
            return 'different_netns'
    except BoundaryDenied:
        pass  # Cross-UID /proc inspection may be denied by the kernel.
    if _tcp_socket_families_denied():
        return 'tcp_socket_families_denied'
    raise BoundaryDenied('network isolation not established')


def _no_inherited_socket_capabilities():
    """Reject sockets already open before AF_INET/AF_INET6 creation policy.

    An inherited connected CDP descriptor can bypass address-family creation
    restrictions. This is a point-in-time check, not an FD-receive sandbox.
    """
    try:
        names = os.listdir('/proc/self/fd')
    except OSError as exc:
        raise BoundaryDenied('inherited FD inventory unavailable') from exc
    for name in names:
        if not name.isdecimal() or int(name) <= 2:
            continue
        try:
            duplicate = os.dup(int(name))
        except OSError as exc:
            if exc.errno == errno.EBADF:  # ephemeral proc directory FD
                continue
            raise BoundaryDenied('inherited FD inspection ambiguous') from exc
        try:
            endpoint = socket.socket(fileno=duplicate)
        except OSError as exc:
            os.close(duplicate)
            if exc.errno in (errno.ENOTSOCK, errno.EINVAL, errno.EBADF):
                continue
            raise BoundaryDenied('inherited FD type ambiguous') from exc
        with endpoint:
            if endpoint.family in (socket.AF_INET, socket.AF_INET6):
                raise BoundaryDenied('inherited network socket capability')
            if endpoint.family == socket.AF_UNIX:
                try:
                    endpoint.getpeername()
                except OSError as exc:
                    if exc.errno not in (errno.ENOTCONN, errno.EINVAL):
                        raise BoundaryDenied('inherited Unix socket state ambiguous') from exc
                else:
                    raise BoundaryDenied('inherited connected Unix socket capability')


def _profile_denied(path):
    _canonical_path(path)
    try:
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    except OSError as exc:
        if exc.errno in (errno.EACCES, errno.EPERM):
            return
        # Missing or symlinked path does not prove an inaccessible real profile.
        raise BoundaryDenied('profile denial not established') from exc
    else:
        os.close(fd)
        raise BoundaryDenied('observer can read browser profile directory')


def _cdp_denied(host, port):
    if host not in ('127.0.0.1', '::1') or type(port) is not int or not 0 < port < 65536:
        raise BoundaryDenied('numeric loopback CDP endpoint required')
    family = socket.AF_INET if host == '127.0.0.1' else socket.AF_INET6
    try:
        probe = socket.socket(family, socket.SOCK_STREAM)
    except OSError as exc:
        if exc.errno in (errno.EAFNOSUPPORT, errno.EPERM, errno.EACCES):
            return  # e.g. systemd RestrictAddressFamilies=AF_UNIX
        raise BoundaryDenied('CDP socket creation ambiguous') from exc
    with probe as s:
        s.settimeout(0.5)
        try:
            s.connect((host, port))
        except OSError as exc:
            if exc.errno in (errno.ECONNREFUSED, errno.ENETUNREACH,
                             errno.EHOSTUNREACH, errno.EACCES, errno.EPERM):
                return
            raise BoundaryDenied('CDP connectivity ambiguous') from exc
    raise BoundaryDenied('observer can connect to declared CDP endpoint')


def _snapshot_peer(path, collector_uid):
    _canonical_path(path)
    try:
        info = os.lstat(path)
        if not stat.S_ISSOCK(info.st_mode) or info.st_uid != collector_uid or info.st_mode & 0o002:
            raise BoundaryDenied('snapshot socket type/owner/mode denied')
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            s.connect(path)
            raw = s.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize('3i'))
            pid, uid, gid = struct.unpack('3i', raw)
            if pid <= 0 or uid != collector_uid or gid < 0:
                raise BoundaryDenied('snapshot server peer UID mismatch')
        after = os.lstat(path)
        if (info.st_dev, info.st_ino) != (after.st_dev, after.st_ino):
            raise BoundaryDenied('snapshot endpoint replaced during check')
    except OSError as exc:
        raise BoundaryDenied('snapshot endpoint not reachable and pinned') from exc


def audit_observer_boundary(*, collector_pid, collector_uid, profile,
                            snapshot_socket, cdp_host='127.0.0.1', cdp_port=9222):
    """Run from the observer's own unprivileged process; deny on unknowns.

    This measures a *declared* boundary at one instant, not all possible CDP
    addresses or the future state of the machine. Never use it as admission.
    """
    if (os.name != 'posix' or not Path('/proc/self/ns/net').exists()
            or type(collector_pid) is not int or collector_pid <= 1
            or type(collector_uid) is not int or collector_uid <= 0
            or os.geteuid() in (0, collector_uid)):
        raise BoundaryDenied('distinct non-root Linux observer and collector required')
    try:
        process = os.stat(f'/proc/{collector_pid}')
    except OSError as exc:
        raise BoundaryDenied('collector process not inspectable') from exc
    if process.st_uid != collector_uid:
        raise BoundaryDenied('collector PID owner mismatch')
    network_guard = _network_guard(collector_pid)
    _no_inherited_socket_capabilities()
    _profile_denied(profile)
    _cdp_denied(cdp_host, cdp_port)
    _snapshot_peer(snapshot_socket, collector_uid)
    # Recheck PID and network separation after network/socket probes.
    try:
        final_process = os.stat(f'/proc/{collector_pid}')
    except OSError as exc:
        raise BoundaryDenied('collector disappeared during preflight') from exc
    if ((process.st_dev, process.st_ino, process.st_uid)
            != (final_process.st_dev, final_process.st_ino, final_process.st_uid)
            or _network_guard(collector_pid) != network_guard):
        raise BoundaryDenied('collector identity or namespace changed')
    return {'status': 'scoped_preflight_pass_not_attestation',
            'checks': ['distinct_uid', network_guard, 'no_inherited_sockets', 'profile_open_denied',
                       'declared_loopback_cdp_unreachable', 'snapshot_peer_uid'],
            'limits': 'declared endpoints only; no ChatGPT authorship or live wake'}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--collector-pid', type=int, required=True)
    p.add_argument('--collector-uid', type=int, required=True)
    p.add_argument('--browser-profile', required=True)
    p.add_argument('--snapshot-socket', required=True)
    p.add_argument('--cdp-host', default='127.0.0.1')
    p.add_argument('--cdp-port', type=int, default=9222)
    a = p.parse_args(argv)
    try:
        result = audit_observer_boundary(collector_pid=a.collector_pid,
                 collector_uid=a.collector_uid, profile=a.browser_profile,
                 snapshot_socket=a.snapshot_socket, cdp_host=a.cdp_host,
                 cdp_port=a.cdp_port)
    except BoundaryDenied as exc:
        print(json.dumps({'status': 'blocked', 'reason': str(exc)}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
