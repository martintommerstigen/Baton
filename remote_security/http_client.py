"""One-shot Baton Remote client: no proxies, redirects, retries, or UI writes."""
from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import http.client
import json
import os
import secrets
from pathlib import Path
import time
from urllib.parse import urlsplit

from remote_security.envelope_gate import Gate, MAX_PAYLOAD_BYTES
from remote_security.http_ingress import load_bearer_token, load_private_key
from remote_security.admission_mac import admission_mac


class DeliveryUncertain(RuntimeError):
    """The server may have committed; never automatically resend."""


def send_once(base_url, bearer, sender_key, envelope, payload, timeout=3):
    parsed = urlsplit(base_url)
    if (parsed.scheme != 'http' or parsed.hostname != '127.0.0.1'
            or parsed.username is not None or parsed.password is not None
            or parsed.path not in ('', '/') or parsed.query or parsed.fragment
            or parsed.port is None):
        raise ValueError('only explicit http://127.0.0.1:PORT accepted; use SSH forwarding')
    if not isinstance(payload, bytes) or len(payload) > MAX_PAYLOAD_BYTES:
        raise ValueError('payload must be at most 65536 bytes')
    if not isinstance(bearer, bytes) or not 32 <= len(bearer) <= 128 or any(c < 33 or c > 126 for c in bearer):
        raise ValueError('invalid bearer')
    signature = Gate.sign(envelope, sender_key)
    body = json.dumps({'envelope': envelope, 'signature': signature,
                       'payload_b64': base64.b64encode(payload).decode('ascii')},
                      separators=(',', ':'), sort_keys=True).encode('utf-8')
    nonce = secrets.token_hex(16)
    expected_mac = admission_mac(sender_key, nonce, envelope, 'accepted_not_delivered')
    connection = http.client.HTTPConnection('127.0.0.1', parsed.port, timeout=timeout)
    try:
        # No proxy or redirect handler; a 302 is an error, never followed.
        connection.request('POST', '/v1/envelopes', body=body, headers={
            'Host': '127.0.0.1:%d' % parsed.port,
            'Authorization': 'Bearer ' + bearer.decode('ascii'),
            'X-Baton-Receipt-Nonce': nonce,
            'Content-Type': 'application/json',
            'Content-Length': str(len(body)),
        })
        response = connection.getresponse()
        raw = response.read(2049)
        if len(raw) > 2048:
            raise DeliveryUncertain('oversized response; delivery unknown')
        if response.status != 202:
            raise DeliveryUncertain('server did not confirm admission; no automatic retry')
        macs = response.headers.get_all('X-Baton-Receipt-MAC', [])
        if len(macs) != 1 or not hmac.compare_digest(macs[0], expected_mac):
            raise DeliveryUncertain('unauthenticated admission receipt; do not retry')
        data = json.loads(raw)
        if data != {'state': 'accepted_not_delivered'}:
            raise DeliveryUncertain('unexpected receipt; no automatic retry')
        return data['state']
    except (OSError, http.client.HTTPException, UnicodeError, ValueError) as exc:
        raise DeliveryUncertain('transport/readback uncertain; do not retry blindly') from exc
    finally:
        connection.close()


def load_private_payload(path):
    # No unreviewed paths: explicit owner-only regular file, bounded read.
    from remote_security.private_store import _validate_path
    import stat
    p = _validate_path(path)
    flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0)
    fd = os.open(p, flags)
    try:
        s = os.fstat(fd)
        if not stat.S_ISREG(s.st_mode) or s.st_uid != os.getuid() or s.st_mode & 0o077 or s.st_nlink != 1:
            raise PermissionError('payload must be owner-only regular file')
        payload = os.read(fd, MAX_PAYLOAD_BYTES + 1)
        if not payload or len(payload) > MAX_PAYLOAD_BYTES:
            raise ValueError('payload must contain 1..65536 bytes')
        return payload
    finally:
        os.close(fd)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Send one signed envelope to loopback Baton ingress')
    parser.add_argument('--url', default='http://127.0.0.1:8788')
    parser.add_argument('--sender', required=True)
    parser.add_argument('--target', required=True)
    parser.add_argument('--message-id', required=True, help='stable caller-provisioned unique ID; never silently regenerate on failure')
    parser.add_argument('--token-file', required=True)
    parser.add_argument('--sender-key-file', required=True)
    parser.add_argument('--payload-file', required=True)
    args = parser.parse_args(argv)
    payload = load_private_payload(args.payload_file)
    envelope = dict(version=1, sender=args.sender, target=args.target,
                    message_id=args.message_id, issued_at=int(time.time()),
                    action='wake_request', payload_sha256=hashlib.sha256(payload).hexdigest())
    # Print ID before submission so a timeout does not erase its identity.
    print('message_id=' + args.message_id, flush=True)
    print('state=' + send_once(args.url, load_bearer_token(args.token_file),
                               load_private_key(args.sender_key_file), envelope, payload))


if __name__ == '__main__':
    main()
