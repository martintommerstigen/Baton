"""B5 negative tests: loopback 202 is not authenticated without a receipt MAC.

A malicious local listener can impersonate an HTTP port, so the client must
refuse a fabricated durable-admission claim even when HTTP status is 202.
No UI or external network is involved.
"""
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import threading
import time
import unittest

from remote_security.admission_mac import admission_mac
from remote_security.http_client import DeliveryUncertain, send_once


class FakeReceiptHandler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def do_POST(self):
        raw = self.rfile.read(int(self.headers['Content-Length']))
        doc = json.loads(raw)
        nonce = self.headers.get('X-Baton-Receipt-Nonce')
        self.server.seen.append((doc, nonce))
        mode = self.server.mode
        mac = None
        if mode == 'wrong_key':
            mac = admission_mac(b'F' * 48, nonce, doc['envelope'],
                                'accepted_not_delivered')
        elif mode == 'old_nonce':
            mac = admission_mac(b'K' * 48, 'b' * 32, doc['envelope'],
                                'accepted_not_delivered')
        elif mode == 'duplicate_mac':
            mac = admission_mac(b'K' * 48, nonce, doc['envelope'],
                                'accepted_not_delivered')
        elif mode == 'wrong_envelope':
            other = dict(doc['envelope'])
            other['message_id'] = 'different000'
            mac = admission_mac(b'K' * 48, nonce, other,
                                'accepted_not_delivered')
        body = b'{"state":"accepted_not_delivered"}'
        self.send_response(202)
        self.send_header('Content-Type', 'application/json')
        if mac is not None:
            self.send_header('X-Baton-Receipt-MAC', mac)
            if mode == 'duplicate_mac':
                self.send_header('X-Baton-Receipt-MAC', mac)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class ReceiptAuthenticationTests(unittest.TestCase):
    def test_mac_binds_nonce_envelope_and_state(self):
        e = dict(version=1, sender='sender000', target='target000',
                 message_id='message000', issued_at=100,
                 action='wake_request', payload_sha256=hashlib.sha256(b'x').hexdigest())
        a = admission_mac(b'K' * 48, 'a' * 32, e, 'accepted_not_delivered')
        self.assertEqual(len(a), 64)
        self.assertNotEqual(a, admission_mac(b'K' * 48, 'b' * 32, e,
                                             'accepted_not_delivered'))
        with self.assertRaises(ValueError):
            admission_mac(b'K' * 48, 'a' * 32, e, 'delivered')

    def test_fake_202_is_never_promoted_to_authenticated_admission(self):
        server = HTTPServer(('127.0.0.1', 0), FakeReceiptHandler)
        server.seen = []
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            for mode in ('unsigned', 'wrong_key', 'old_nonce', 'wrong_envelope', 'duplicate_mac'):
                with self.subTest(mode=mode):
                    server.mode = mode
                    payload = b'approved'
                    envelope = dict(version=1, sender='sender000', target='target000',
                                    message_id='message000', issued_at=int(time.time()),
                                    action='wake_request',
                                    payload_sha256=hashlib.sha256(payload).hexdigest())
                    with self.assertRaises(DeliveryUncertain):
                        send_once('http://127.0.0.1:%d' % server.server_port,
                                  b'T' * 48, b'K' * 48, envelope, payload)
            self.assertEqual(len(server.seen), 5)
            self.assertTrue(all(len(nonce) == 32 for _, nonce in server.seen))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)


if __name__ == '__main__':
    unittest.main()
