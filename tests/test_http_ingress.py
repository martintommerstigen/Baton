import base64
import hashlib
import http.client
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest

from remote_security.envelope_gate import Gate
from remote_security.http_ingress import IngressServer, load_private_key, load_bearer_token


class IngressTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.token = b'T' * 48
        self.key = b'K' * 48
        self.gate = Gate(str(self.root / 'receipts.sqlite'), {'sender000': self.key},
                         {'sender000'}, {'target000'})
        self.server = IngressServer(0, self.token, self.gate)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.e = dict(version=1, sender='sender000', target='target000',
                      message_id='message000', issued_at=int(time.time()),
                      action='wake_request', payload_sha256=hashlib.sha256(b'approved').hexdigest())

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        self.gate.db.close()
        self.temp.cleanup()

    def request(self, body=None, token=None, host=None, extra=None, method='POST'):
        if body is None:
            body = json.dumps({'envelope': self.e, 'signature': Gate.sign(self.e, self.key),
                               'payload_b64': base64.b64encode(b'approved').decode()}).encode()
        headers = {'Host': host if host is not None else '127.0.0.1:%d' % self.server.server_port,
                   'Authorization': 'Bearer ' + (token if token is not None else self.token).decode(),
                   'Content-Type': 'application/json'}
        headers.update(extra or {})
        c = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=3)
        try:
            c.request(method, '/v1/envelopes', body=body, headers=headers)
            response = c.getresponse()
            return response.status, json.loads(response.read())['state']
        finally:
            c.close()

    def test_bound_loopback_only(self):
        self.assertEqual(self.server.server_address[0], '127.0.0.1')

    def test_valid_signed_payload_accepted_not_delivered(self):
        self.assertEqual(self.request(), (202, 'accepted_not_delivered'))
        self.assertEqual(self.gate.db.execute('SELECT state FROM receipts').fetchone()[0], 'accepted_not_delivered')

    def test_replay_rejected(self):
        self.assertEqual(self.request()[0], 202)
        self.assertEqual(self.request()[0], 400)
        self.assertEqual(self.gate.db.execute('SELECT COUNT(*) FROM receipts').fetchone()[0], 1)

    def test_wrong_token_and_forged_host(self):
        self.assertEqual(self.request(token=b'X' * 48)[0], 401)
        self.assertEqual(self.request(host='evil.example')[0], 403)
        self.assertEqual(self.gate.db.execute('SELECT COUNT(*) FROM receipts').fetchone()[0], 0)

    def test_tampered_payload_no_reservation(self):
        doc = {'envelope': self.e, 'signature': Gate.sign(self.e, self.key),
               'payload_b64': base64.b64encode(b'wrong').decode()}
        self.assertEqual(self.request(json.dumps(doc).encode())[0], 400)
        self.assertEqual(self.request()[0], 202)

    def test_duplicate_json_keys(self):
        self.assertEqual(self.request(b'{"envelope":{},"envelope":{},"signature":"x","payload_b64":""}')[0], 400)

    def test_oversized_request(self):
        self.assertEqual(self.request(body=b'x' * 90001)[0], 413)
        self.assertEqual(self.gate.db.execute('SELECT COUNT(*) FROM receipts').fetchone()[0], 0)

    def test_read_only_methods(self):
        self.assertEqual(self.request(method='GET')[0], 405)

    def test_fifo_key_rejected_without_blocking(self):
        fifo = self.root / 'fifo'
        os.mkfifo(fifo, 0o600)
        with self.assertRaises(PermissionError):
            load_private_key(fifo)

    def test_bearer_token_rejects_newlines(self):
        token_file = self.root / 'token'
        token_file.write_bytes(b'A' * 48 + b'\n')
        token_file.chmod(0o600)
        with self.assertRaises(ValueError):
            load_bearer_token(token_file)

    def test_key_file_symlink_and_permissions(self):
        secret = self.root / 'key'
        secret.write_bytes(self.key)
        secret.chmod(0o600)
        self.assertEqual(load_private_key(secret), self.key)
        secret.chmod(0o644)
        with self.assertRaises(PermissionError):
            load_private_key(secret)
        secret.chmod(0o600)
        link = self.root / 'link'
        link.symlink_to(secret)
        with self.assertRaises(Exception):
            load_private_key(link)


if __name__ == '__main__':
    unittest.main()
