"""B5 negative route-policy tests: a valid sender key is not universal authority.

Only explicit SENDER=TARGET grants in the receive-only HTTP CLI authorize
admission. These tests never open a browser or wake an existing conversation.
"""
import hashlib
from pathlib import Path
import tempfile
import time
import unittest

from remote_security.envelope_gate import Gate, Rejected
from remote_security.http_ingress import main, parse_routes


class RoutePolicyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.tmp.name) / 'receipts.sqlite')
        self.keys = {'sender000': b'a' * 32, 'sender111': b'b' * 32}
        self.targets = {'target000', 'target111'}
        self.routes = {'sender000': {'target000'}, 'sender111': {'target111'}}

    def tearDown(self):
        self.tmp.cleanup()

    def envelope(self, sender, target, mid):
        return dict(version=1, sender=sender, target=target,
                    message_id=mid, issued_at=int(time.time()),
                    action='wake_request',
                    payload_sha256=hashlib.sha256(b'approved').hexdigest())

    def test_cross_sender_target_rejected_before_reservation(self):
        gate = Gate(self.db, self.keys, self.keys, self.targets,
                    allowed_routes=self.routes)
        try:
            wrong = self.envelope('sender000', 'target111', 'message000')
            with self.assertRaisesRegex(Rejected, 'route'):
                gate.accept_payload(wrong, Gate.sign(wrong, self.keys['sender000']), b'approved')
            self.assertEqual(gate.db.execute('SELECT COUNT(*) FROM receipts').fetchone()[0], 0)
            correct = self.envelope('sender000', 'target000', 'message000')
            self.assertEqual(gate.accept_payload(correct, Gate.sign(correct, self.keys['sender000']),
                                                 b'approved'), 'accepted_not_delivered')
            self.assertEqual(gate.db.execute('SELECT COUNT(*) FROM receipts').fetchone()[0], 1)
        finally:
            gate.db.close()

    def test_both_senders_have_distinct_allowed_targets(self):
        gate = Gate(self.db, self.keys, self.keys, self.targets,
                    allowed_routes=self.routes)
        try:
            for sender, target, mid in (
                ('sender000', 'target000', 'message000'),
                ('sender111', 'target111', 'message111'),
            ):
                envelope = self.envelope(sender, target, mid)
                self.assertEqual(gate.accept_payload(envelope, Gate.sign(envelope, self.keys[sender]),
                                                     b'approved'), 'accepted_not_delivered')
            self.assertEqual(gate.db.execute('SELECT COUNT(*) FROM receipts').fetchone()[0], 2)
        finally:
            gate.db.close()

    def test_route_parser_fails_closed(self):
        for items in (
            [], ['sender000=target000'],  # second sender has no route
            ['sender000=target000', 'sender111=target000', 'sender111=target000'],
            ['sender000=target111', 'sender111=target999'],
            ['sender000=target000', 'sender999=target111'],
            ['sender000:target000', 'sender111=target111'],
        ):
            with self.subTest(items=items), self.assertRaises(ValueError):
                parse_routes(items, self.keys, self.targets)
        self.assertEqual(
            parse_routes(['sender000=target000', 'sender111=target111'], self.keys, self.targets),
            self.routes,
        )

    def test_invalid_route_policy_fails_before_opening_database(self):
        for routes in (
            {}, {'sender000': {'target000'}},
            {'sender000': {'target000'}, 'sender111': set()},
            {'sender000': {'target000'}, 'sender111': {'notallowed'}},
            {'sender000': 'target000', 'sender111': {'target111'}},
        ):
            with self.subTest(routes=routes), self.assertRaises(Rejected):
                Gate(self.db, self.keys, self.keys, self.targets, allowed_routes=routes)
            self.assertFalse(Path(self.db).exists())

    def test_http_cli_refuses_missing_route_before_opening_keys(self):
        with self.assertRaises(SystemExit) as ctx:
            main(['--database', self.db, '--token-file', '/does/not/exist',
                  '--sender-key-file', 'sender000=/does/not/exist',
                  '--target', 'target000'])
        self.assertEqual(ctx.exception.code, 2)
        self.assertFalse(Path(self.db).exists())


if __name__ == '__main__':
    unittest.main()
