"""Read-only B5 receipt reconciliation after uncertain HTTP admission.

A persisted receipt is evidence of local admission, never proof of delivery,
source completeness, or a ChatGPT assistant turn. Absence is UNKNOWN, not a
permission to resend. No network calls, UI writes, or automatic retries.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import sqlite3
import stat

from remote_security.private_store import _validate_path

IDENT = re.compile(r"[A-Za-z0-9_-]{8,96}\\Z")
DIGEST = re.compile(r"[0-9a-f]{64}\\Z")
EXPECTED_KEYS = frozenset({
    'version', 'sender', 'target', 'message_id', 'issued_at',
    'action', 'payload_sha256',
})


class AuditError(ValueError):
    """The receipt store is inaccessible or violates the local trust policy."""


def _canonical(envelope):
    return json.dumps(envelope, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=True, allow_nan=False).encode('ascii')


def _open_readonly(path):
    # Unlike secure_database_path, do not create a database on lookup.
    try:
        p = _validate_path(path)
        s = p.lstat()
    except (OSError, ValueError) as exc:
        raise AuditError('missing_or_unsafe_database') from exc
    if (not stat.S_ISREG(s.st_mode) or s.st_uid != os.getuid()
            or s.st_mode & 0o077 or s.st_nlink != 1):
        raise AuditError('unsafe_database_file')
    # pathlib.as_uri percent-encodes URI metacharacters in filenames.
    try:
        db = sqlite3.connect(p.as_uri() + '?mode=ro', uri=True, timeout=3)
    except sqlite3.Error as exc:
        raise AuditError('database_open_failed') from exc
    try:
        db.execute('PRAGMA query_only=ON')
        db.execute('BEGIN')  # consistent read snapshot of both tables
    except Exception:
        db.close()
        raise
    return db


def audit_receipt(database, sender, message_id, sender_key):
    """Return one of four conservative local receipt classifications.

    The sender key is required to authenticate a stored payload record. A
    legacy envelope-only receipt cannot be independently authenticated here.
    Neither a present nor an absent record authorizes any new transmission.
    """
    if (not isinstance(sender, str) or not IDENT.fullmatch(sender)
            or not isinstance(message_id, str) or not IDENT.fullmatch(message_id)
            or not isinstance(sender_key, bytes) or len(sender_key) < 32):
        raise AuditError('invalid_audit_parameters')
    db = _open_readonly(database)
    try:
        receipt = db.execute(
            'SELECT digest,state FROM receipts WHERE sender=? AND msg=?',
            (sender, message_id),
        ).fetchone()
        payload_record = db.execute(
            'SELECT envelope,payload,signature FROM payloads WHERE sender=? AND msg=?',
            (sender, message_id),
        ).fetchone()
    except sqlite3.DatabaseError as exc:
        raise AuditError('unreadable_receipt_schema') from exc
    finally:
        db.close()
    if receipt is None:
        return {'classification': 'corrupt_untrusted' if payload_record is not None else 'absent_unknown',
                'send_permitted': False}
    fingerprint, state = receipt
    if state != 'accepted_not_delivered' or not isinstance(fingerprint, str) or not DIGEST.fullmatch(fingerprint):
        return {'classification': 'corrupt_untrusted', 'send_permitted': False}
    if payload_record is None:
        return {'classification': 'present_envelope_only_unverified', 'send_permitted': False}
    raw_envelope, payload, signature = payload_record
    try:
        if (not isinstance(raw_envelope, bytes) or not isinstance(payload, bytes)
                or not isinstance(signature, str) or len(payload) > 65536):
            raise ValueError('record types')
        envelope = json.loads(raw_envelope.decode('ascii'))
        if (not isinstance(envelope, dict) or set(envelope) != EXPECTED_KEYS
                or type(envelope['version']) is not int or envelope['version'] != 1
                or envelope['sender'] != sender or envelope['message_id'] != message_id
                or not isinstance(envelope['target'], str)
                or not IDENT.fullmatch(envelope['target'])
                or envelope['action'] != 'wake_request'
                or type(envelope['issued_at']) is not int
                or not isinstance(envelope['payload_sha256'], str)
                or not DIGEST.fullmatch(envelope['payload_sha256'])):
            raise ValueError('schema')
        canonical = _canonical(envelope)
        if canonical != raw_envelope:
            raise ValueError('noncanonical')
        if not hmac.compare_digest(hashlib.sha256(canonical).hexdigest(), fingerprint):
            raise ValueError('receipt fingerprint')
        if not hmac.compare_digest(hashlib.sha256(payload).hexdigest(), envelope['payload_sha256']):
            raise ValueError('payload mismatch')
        expected = hmac.new(sender_key, canonical, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature):
            raise ValueError('signature mismatch')
    except (ValueError, TypeError, UnicodeError, KeyError):
        return {'classification': 'corrupt_untrusted', 'send_permitted': False}
    return {'classification': 'present_authenticated_payload',
            'admission_state': 'accepted_not_delivered', 'send_permitted': False}


def main(argv=None):
    parser = argparse.ArgumentParser(description='Read-only local admission audit; NEVER authorizes retry')
    parser.add_argument('--database', required=True)
    parser.add_argument('--sender', required=True)
    parser.add_argument('--message-id', required=True)
    parser.add_argument('--sender-key-file', required=True)
    args = parser.parse_args(argv)
    from remote_security.http_ingress import load_private_key
    result = audit_receipt(args.database, args.sender, args.message_id,
                           load_private_key(args.sender_key_file))
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
