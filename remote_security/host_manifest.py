"""Read-only B5 host observation: source-file hashes, socket UID and pause marker.

This is a *local process assertion*, not remote host attestation, live RustWorld
measurement or existing-chat wake. No network, shell, source job or UI writes.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
import socket
from pathlib import Path
import stat

from remote_security.source_broker_probe import probe, ProbeUncertain, UntrustedBroker


class ManifestUncertain(RuntimeError):
    """Unsafe or ambiguous local observation; no automatic retry."""


def _canonical(path):
    raw = os.fspath(path)
    if (type(raw) is not str or not raw.startswith('/') or raw == '/'
            or any(part in ('', '.', '..') for part in raw.split('/')[1:])):
        raise ManifestUncertain('noncanonical absolute path')
    return Path(raw)


def _safe_parent(path):
    current = Path('/')
    for part in path.parent.parts[1:]:
        current = current / part
        try:
            s = current.lstat()
        except OSError as exc:
            raise ManifestUncertain('unavailable parent directory') from exc
        if not stat.S_ISDIR(s.st_mode):
            raise ManifestUncertain('non-directory or symlink ancestor')
        if s.st_mode & 0o022 and not (s.st_uid == 0 and s.st_mode & stat.S_ISVTX):
            raise ManifestUncertain('mutable ancestor directory')


def pause_marker(path):
    """Observe only existence at an explicit path; absence is NOT UI permission."""
    if path is None:
        return 'not_checked'
    p = _canonical(path)
    _safe_parent(p)
    try:
        s = p.lstat()
    except FileNotFoundError:
        return 'absent_at_checked_path_not_authorization'
    except OSError as exc:
        raise ManifestUncertain('pause marker metadata unavailable') from exc
    if not stat.S_ISREG(s.st_mode) or s.st_nlink != 1:
        raise ManifestUncertain('unsafe pause marker type or links')
    return 'present_at_checked_path'


def _source_file_digest(path):
    """Hash bytes on disk, explicitly not a hash of executing instructions."""
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | getattr(os, 'O_CLOEXEC', 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise ManifestUncertain('source file unavailable') from exc
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise ManifestUncertain('unsafe source file type')
        h = hashlib.sha256()
        total = 0
        while True:
            block = os.read(fd, 65536)
            if not block:
                break
            total += len(block)
            if total > 2_000_000:
                raise ManifestUncertain('source file exceeds bounded read')
            h.update(block)
        after = os.fstat(fd)
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
                after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
            raise ManifestUncertain('source file changed while reading')
        return h.hexdigest()
    finally:
        os.close(fd)


def _socket_metadata(path, expected_uid):
    """Post-probe pathname snapshot; inode is NOT a stable host attestation."""
    p = _canonical(path)
    _safe_parent(p)
    try:
        st = p.lstat()
    except OSError as exc:
        raise ManifestUncertain('socket metadata unavailable after probe') from exc
    if (not stat.S_ISSOCK(st.st_mode) or st.st_uid != expected_uid
            or st.st_mode & 0o777 != 0o660 or st.st_nlink != 1):
        raise ManifestUncertain('socket metadata changed after probe')
    return {'device': st.st_dev, 'inode': st.st_ino, 'owner_uid': st.st_uid,
            'mode_octal': '0660', 'scope': 'post_probe_path_snapshot_not_atomic'}


def manifest(socket_path, service_uid, *, pause_path=None, connect=False):
    """Make exactly one optional kernel contact; never send application bytes."""
    if type(connect) is not bool:
        raise ValueError('connect must be bool')
    from remote_security import source_broker, source_broker_probe
    endpoint = probe(socket_path, service_uid, connect=connect)
    socket_metadata = _socket_metadata(socket_path, service_uid)
    hashes = {
        'source_broker.py': _source_file_digest(source_broker.__file__),
        'source_broker_probe.py': _source_file_digest(source_broker_probe.__file__),
        'host_manifest.py': _source_file_digest(__file__),
    }
    pause = pause_marker(pause_path)
    return {
        'schema': 'baton.local_observation.v1',
        'evidence_scope': 'self_reported_local_metadata_not_remote_attestation',
        'observed_utc': datetime.now(timezone.utc).isoformat(),
        'observer_uid': os.geteuid(),
        'socket_observation': endpoint,
        'socket_inode_snapshot': socket_metadata,
        'source_file_sha256_not_runtime_attestation': hashes,
        'pause_marker': pause,
        'pause_authorization': 'never_inferred',
        'ui_write': 'not_attempted',
        'source_capture': 'not_attempted',
        'greg_live': 'not_established',
        'existing_chat_wake': 'not_established',
        'automatic_retry': False,
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--socket', required=True)
    p.add_argument('--service-uid', required=True, type=int)
    p.add_argument('--pause-file', help='explicit path to observe; absence never authorizes writes')
    p.add_argument('--connect-once', action='store_true', help='opt-in one AF_UNIX connection, zero request bytes')
    args = p.parse_args(argv)
    try:
        result = manifest(args.socket, args.service_uid, pause_path=args.pause_file,
                          connect=args.connect_once)
    except (ManifestUncertain, ProbeUncertain, UntrustedBroker, OSError, ValueError) as exc:
        print(json.dumps({'state': 'rejected_or_uncertain_no_retry',
                          'error_type': type(exc).__name__}, sort_keys=True))
        return 3
    print(json.dumps(result, sort_keys=True, separators=(',', ':')))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
