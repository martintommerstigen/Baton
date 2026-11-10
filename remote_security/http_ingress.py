"""Authenticated, loopback-only, receive-only Baton envelope ingress.

No UI operations, shell, arbitrary path access, or blind retry. A 202 response
means only that a signed, body-bound envelope was durably accepted, NOT that a
ChatGPT conversation was contacted or woke.
"""
from __future__ import annotations

import argparse
import base64
import binascii
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import re
import stat

from remote_security.envelope_gate import Gate, Rejected
from remote_security.private_store import _validate_path

MAX_REQUEST_BYTES = 90000


def load_private_key(path):
    p = _validate_path(path)
    flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_CLOEXEC', 0)
    fd = os.open(p, flags)
    try:
        s = os.fstat(fd)
        if (not stat.S_ISREG(s.st_mode) or s.st_uid != os.getuid()
                or s.st_mode & 0o077 or s.st_nlink != 1):
            raise PermissionError('key file must be owner-owned regular mode 0600, no hardlinks')
        data = os.read(fd, 257)
        if not 32 <= len(data) <= 256:
            raise ValueError('key must contain 32..256 raw bytes')
        return data
    finally:
        os.close(fd)


def load_bearer_token(path):
    token = load_private_key(path)
    if len(token) > 128 or any(c < 33 or c > 126 for c in token):
        raise ValueError('bearer token must be 32..128 printable ASCII bytes without whitespace')
    return token


def _unique_pairs(pairs):
    result = {}
    for k, v in pairs:
        if k in result:
            raise ValueError('duplicate JSON key')
        result[k] = v
    return result


class IngressServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    request_queue_size = 8

    def __init__(self, port, token, gate):
        if not isinstance(token, bytes) or len(token) < 32:
            raise ValueError('bearer token must be 32+ bytes')
        self.token = token
        self.gate = gate
        super().__init__(('127.0.0.1', port), IngressHandler)

    def get_request(self):
        sock, address = super().get_request()
        sock.settimeout(3)
        return sock, address


class IngressHandler(BaseHTTPRequestHandler):
    server_version = 'BatonIngress/0.1'
    sys_version = ''
    protocol_version = 'HTTP/1.0'

    def log_message(self, format, *args):
        pass  # Never log headers, secrets, paths or payloads.

    def _reply(self, code, state):
        raw = json.dumps({'state': state}, separators=(',', ':')).encode('ascii')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Connection', 'close')
        self.end_headers()
        self.wfile.write(raw)
        self.close_connection = True

    def do_POST(self):
        host = self.headers.get_all('Host', [])
        expected_host = '127.0.0.1:%d' % self.server.server_port
        if host != [expected_host]:
            return self._reply(403, 'host_rejected')
        auth = self.headers.get_all('Authorization', [])
        expected_auth = b'Bearer ' + self.server.token
        if len(auth) != 1 or not hmac.compare_digest(auth[0].encode('utf-8'), expected_auth):
            return self._reply(401, 'unauthorized')
        if self.path != '/v1/envelopes' or self.headers.get('Content-Type') != 'application/json':
            return self._reply(404, 'operation_not_allowlisted')
        lengths = self.headers.get_all('Content-Length', [])
        if (len(lengths) != 1 or not re.fullmatch('[0-9]{1,6}', lengths[0])
                or self.headers.get('Transfer-Encoding') is not None
                or self.headers.get('Expect') is not None):
            return self._reply(400, 'invalid_framing')
        length = int(lengths[0])
        if length > MAX_REQUEST_BYTES:
            return self._reply(413, 'oversized_request')
        try:
            raw = self.rfile.read(length)
            if len(raw) != length:
                return self._reply(400, 'truncated_request')
            doc = json.loads(raw.decode('utf-8'), object_pairs_hook=_unique_pairs)
            if not isinstance(doc, dict) or set(doc) != {'envelope', 'signature', 'payload_b64'}:
                return self._reply(400, 'invalid_schema')
            if not isinstance(doc['payload_b64'], str):
                return self._reply(400, 'invalid_payload')
            payload = base64.b64decode(doc['payload_b64'], validate=True)
            state = self.server.gate.accept_payload(doc['envelope'], doc['signature'], payload)
        except (UnicodeError, ValueError, TypeError, binascii.Error, RecursionError, Rejected):
            return self._reply(400, 'rejected')
        return self._reply(202, state)

    def do_GET(self):
        self._reply(405, 'method_not_allowed')

    do_PUT = do_GET
    do_DELETE = do_GET


def main(argv=None):
    parser = argparse.ArgumentParser(description='Loopback-only receive-only Baton ingress')
    parser.add_argument('--port', type=int, default=8788)
    parser.add_argument('--database', required=True)
    parser.add_argument('--token-file', required=True)
    parser.add_argument('--sender-key-file', action='append', required=True, metavar='SENDER=PATH')
    parser.add_argument('--target', action='append', required=True)
    args = parser.parse_args(argv)
    keys = {}
    for item in args.sender_key_file:
        sender, sep, path = item.partition('=')
        if not sep or sender in keys or not sender:
            parser.error('sender key syntax must be unique SENDER=PATH')
        keys[sender] = load_private_key(path)
    gate = Gate(args.database, keys, keys, args.target)
    try:
        with IngressServer(args.port, load_bearer_token(args.token_file), gate) as server:
            print('Baton receive-only ingress on 127.0.0.1:%d' % server.server_port, flush=True)
            server.serve_forever()
    finally:
        gate.db.close()


if __name__ == '__main__':
    main()
