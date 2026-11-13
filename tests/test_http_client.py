import hashlib
import io
from contextlib import redirect_stdout
import tempfile
import time
import unittest
from pathlib import Path
from remote_security.envelope_gate import Gate
from remote_security.http_ingress import IngressServer
from remote_security.http_client import send_once, DeliveryUncertain, load_private_payload
from remote_security import http_client
import threading


class ClientTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.key = b'K' * 48
        self.token = b'T' * 48
        self.g = Gate(str(self.root / 'r.sqlite'), {'sender000': self.key}, {'sender000'}, {'target000'})
        self.s = IngressServer(0, self.token, self.g)
        self.t = threading.Thread(target=self.s.serve_forever, daemon=True)
        self.t.start()
        self.url = 'http://127.0.0.1:%d' % self.s.server_port
        self.payload = b'approved'
        self.e = dict(version=1, sender='sender000', target='target000', message_id='message000',
                      issued_at=int(time.time()), action='wake_request',
                      payload_sha256=hashlib.sha256(self.payload).hexdigest())

    def tearDown(self):
        self.s.shutdown(); self.s.server_close(); self.t.join(timeout=3)
        self.g.db.close(); self.tmp.cleanup()

    def test_round_trip_one_shot(self):
        self.assertEqual(send_once(self.url, self.token, self.key, self.e, self.payload), 'accepted_not_delivered')
        self.assertEqual(self.g.db.execute('SELECT payload FROM payloads').fetchone()[0], self.payload)

    def test_replay_is_uncertain_not_resent(self):
        send_once(self.url, self.token, self.key, self.e, self.payload)
        with self.assertRaises(DeliveryUncertain):
            send_once(self.url, self.token, self.key, self.e, self.payload)
        self.assertEqual(self.g.db.execute('SELECT COUNT(*) FROM receipts').fetchone()[0], 1)

    def test_wrong_key_never_admitted(self):
        with self.assertRaises(DeliveryUncertain):
            send_once(self.url, self.token, b'X' * 48, self.e, self.payload)
        self.assertEqual(self.g.db.execute('SELECT COUNT(*) FROM receipts').fetchone()[0], 0)

    def test_nonloopback_url_rejected_before_network(self):
        for url in ('http://example.org:8788', 'http://127.0.0.1:8788@evil.org:80',
                    'https://127.0.0.1:8788', 'http://127.0.0.1:8788/evil'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                send_once(url, self.token, self.key, self.e, self.payload)

    def test_cli_defaults_to_https_and_fails_before_plaintext_disclosure(self):
        token_path = self.root / 'cli-token'
        key_path = self.root / 'cli-key'
        payload_path = self.root / 'cli-payload'
        for path, data in ((token_path, self.token), (key_path, self.key),
                           (payload_path, self.payload)):
            path.write_bytes(data)
            path.chmod(0o600)
        args = [
            '--sender', 'sender000', '--target', 'target000',
            '--message-id', 'cli-default-test', '--token-file', str(token_path),
            '--sender-key-file', str(key_path), '--payload-file', str(payload_path),
        ]
        with redirect_stdout(io.StringIO()), self.assertRaisesRegex(
                ValueError, 'HTTPS requires an explicit pinned server certificate'):
            http_client.main(args)
        self.assertEqual(self.g.db.execute(
            'SELECT COUNT(*) FROM receipts').fetchone()[0], 0)

    def test_private_payload_file_rejects_symlink(self):
        p = self.root / 'payload'
        p.write_bytes(self.payload)
        p.chmod(0o600)
        self.assertEqual(load_private_payload(p), self.payload)
        link = self.root / 'link'
        link.symlink_to(p)
        with self.assertRaises(Exception):
            load_private_payload(link)


if __name__ == '__main__':
    unittest.main()
