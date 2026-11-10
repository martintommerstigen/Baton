"""B5 TLS endpoint authentication negative controls (no Greg/UI/external host).

Test certificates and keys are generated ephemerally by OpenSSL; never
committed to Git. A trusted handshake precedes HTTP bearer disclosure.
"""
import hashlib
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import shutil
import ssl
import subprocess
import tempfile
import threading
import time
import unittest

from remote_security.envelope_gate import Gate
from remote_security.http_client import DeliveryUncertain, send_once
from remote_security.http_ingress import TLSIngressServer
from remote_security.tls_endpoint import pinned_client_context, server_tls_context


class CapturingHandler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def do_POST(self):
        self.server.received.append(self.headers.get('Authorization'))
        body = b'ok'
        self.send_response(200)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@unittest.skipUnless(shutil.which('openssl'), 'OpenSSL required for ephemeral TLS test certificates')
class TLSEndpointTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.cert, self.key = self.make_cert('good')
        self.other_cert, self.other_key = self.make_cert('other')

    def tearDown(self):
        self.tmp.cleanup()

    def make_cert(self, name, san='IP:127.0.0.1'):
        cert, key = self.root / (name + '.crt'), self.root / (name + '.key')
        subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes',
                        '-keyout', str(key), '-out', str(cert), '-days', '1',
                        '-subj', '/CN=127.0.0.1', '-addext', 'subjectAltName=' + san],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        cert.chmod(0o600)
        key.chmod(0o600)
        return cert, key

    def start_server(self, cert=None, key=None):
        server = ThreadingHTTPServer(('127.0.0.1', 0), CapturingHandler)
        server.received = []
        ctx = server_tls_context(cert or self.cert, key or self.key)
        original_get_request = server.get_request

        def tls_accept():
            sock, address = original_get_request()
            sock.settimeout(2)
            return ctx.wrap_socket(sock, server_side=True), address

        server.get_request = tls_accept
        runner = threading.Thread(target=server.serve_forever, daemon=True)
        runner.start()
        return server, runner

    def test_trusted_server_receives_bearer_after_handshake(self):
        server, runner = self.start_server()
        try:
            conn = http.client.HTTPSConnection('127.0.0.1', server.server_port,
                                               timeout=2, context=pinned_client_context(self.cert))
            try:
                conn.request('POST', '/', body=b'approved',
                             headers={'Authorization': 'Bearer TEST'})
                response = conn.getresponse()
                self.assertEqual(response.status, 200)
                response.read()
            finally:
                conn.close()
            self.assertEqual(server.received, ['Bearer TEST'])
        finally:
            server.shutdown(); server.server_close(); runner.join(timeout=3)

    def test_wrong_certificate_fails_before_bearer_disclosure(self):
        server, runner = self.start_server(self.other_cert, self.other_key)
        try:
            conn = http.client.HTTPSConnection('127.0.0.1', server.server_port,
                                               timeout=2, context=pinned_client_context(self.cert))
            try:
                with self.assertRaises(ssl.SSLCertVerificationError):
                    conn.request('POST', '/', headers={'Authorization': 'Bearer TEST'})
            finally:
                conn.close()
            self.assertEqual(server.received, [])
        finally:
            server.shutdown(); server.server_close(); runner.join(timeout=3)

    def test_symlink_and_permissive_tls_files_rejected(self):
        link = self.root / 'linked.crt'
        link.symlink_to(self.cert)
        with self.assertRaises((OSError, ValueError, PermissionError)):
            pinned_client_context(link)
        self.key.chmod(0o644)
        with self.assertRaises(PermissionError):
            server_tls_context(self.cert, self.key)
        self.cert.chmod(0o644)
        with self.assertRaises(PermissionError):
            pinned_client_context(self.cert)

    def test_wrong_ip_san_fails_even_if_cert_trusted(self):
        cert, key = self.make_cert('wrongip', 'DNS:localhost')
        server, runner = self.start_server(cert, key)
        try:
            conn = http.client.HTTPSConnection('127.0.0.1', server.server_port,
                                               timeout=2, context=pinned_client_context(cert))
            try:
                with self.assertRaises(ssl.SSLCertVerificationError):
                    conn.request('POST', '/', headers={'Authorization': 'Bearer TEST'})
            finally:
                conn.close()
            self.assertEqual(server.received, [])
        finally:
            server.shutdown(); server.server_close(); runner.join(timeout=3)

    def _envelope(self):
        payload = b'approved harmless wake marker'
        envelope = dict(version=1, sender='sender000', target='target000',
                        message_id='message000', issued_at=int(time.time()),
                        action='wake_request',
                        payload_sha256=hashlib.sha256(payload).hexdigest())
        return envelope, payload

    def test_end_to_end_pinned_tls_admits_once_not_delivered(self):
        key = b'K' * 48
        gate = Gate(str(self.root / 'receipts.sqlite'), {'sender000': key},
                    {'sender000'}, {'target000'})
        server = TLSIngressServer(0, b'T' * 48, gate,
                                  server_tls_context(self.cert, self.key))
        runner = threading.Thread(target=server.serve_forever, daemon=True)
        runner.start()
        try:
            envelope, payload = self._envelope()
            url = 'https://127.0.0.1:%d' % server.server_port
            self.assertEqual(send_once(url, b'T' * 48, key, envelope, payload,
                                       server_cert_file=str(self.cert)),
                             'accepted_not_delivered')
            self.assertEqual(gate.db.execute('SELECT COUNT(*) FROM receipts').fetchone()[0], 1)
            with self.assertRaises(DeliveryUncertain):
                send_once(url, b'T' * 48, key, envelope, payload,
                          server_cert_file=str(self.cert))
            self.assertEqual(gate.db.execute('SELECT COUNT(*) FROM receipts').fetchone()[0], 1)
        finally:
            server.shutdown(); server.server_close(); runner.join(timeout=3)
            gate.db.close()

    def test_untrusted_tls_server_never_receives_authenticated_request(self):
        key = b'K' * 48
        gate = Gate(str(self.root / 'receipts.sqlite'), {'sender000': key},
                    {'sender000'}, {'target000'})
        server = TLSIngressServer(0, b'T' * 48, gate,
                                  server_tls_context(self.other_cert, self.other_key))
        runner = threading.Thread(target=server.serve_forever, daemon=True)
        runner.start()
        try:
            envelope, payload = self._envelope()
            with self.assertRaises(DeliveryUncertain):
                send_once('https://127.0.0.1:%d' % server.server_port,
                          b'T' * 48, key, envelope, payload,
                          server_cert_file=str(self.cert))
            self.assertEqual(gate.db.execute('SELECT COUNT(*) FROM receipts').fetchone()[0], 0)
        finally:
            server.shutdown(); server.server_close(); runner.join(timeout=3)
            gate.db.close()

    def test_missing_pin_or_pin_on_plaintext_rejected_before_connect(self):
        envelope, payload = self._envelope()
        with self.assertRaises(ValueError):
            send_once('https://127.0.0.1:8788', b'T' * 48, b'K' * 48,
                      envelope, payload)
        with self.assertRaises(ValueError):
            send_once('http://127.0.0.1:8788', b'T' * 48, b'K' * 48,
                      envelope, payload, server_cert_file=str(self.cert))


if __name__ == '__main__':
    unittest.main()
