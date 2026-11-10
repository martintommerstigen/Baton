"""Negative B5 tests: file trust boundary, payload integrity, and races."""
import concurrent.futures
import hashlib
import os
from pathlib import Path
import tempfile
import time
import unittest

from remote_security.envelope_gate import Gate, Rejected
from remote_security.private_store import UnsafeStore


def _accept_in_process(db_path, envelope, signature):
    gate = Gate(db_path, {'sender000': b'k' * 32}, {'sender000'}, {'target000'})
    try:
        return gate.accept(envelope, signature)
    except Rejected as exc:
        return str(exc)
    finally:
        gate.db.close()


class HardeningTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db = self.root / 'receipts.sqlite'
        self.key = b'k' * 32
        self.e = dict(version=1, sender='sender000', target='target000',
                      message_id='message000', issued_at=int(time.time()),
                      action='wake_request', payload_sha256=hashlib.sha256(b'approved').hexdigest())

    def tearDown(self):
        self.temp.cleanup()

    def gate(self, db=None):
        return Gate(str(db or self.db), {'sender000': self.key}, {'sender000'}, {'target000'})

    def test_payload_binding_wrong_bytes_does_not_reserve(self):
        g = self.gate()
        sig = Gate.sign(self.e, self.key)
        try:
            with self.assertRaisesRegex(Rejected, 'payload mismatch'):
                g.accept_payload(self.e, sig, b'altered')
            self.assertEqual(g.accept_payload(self.e, sig, b'approved'), 'accepted_not_delivered')
        finally:
            g.db.close()

    def test_payload_size_and_type(self):
        g = self.gate()
        sig = Gate.sign(self.e, self.key)
        try:
            for payload in ('approved', b'x' * 65537):
                with self.assertRaisesRegex(Rejected, 'payload type or size'):
                    g.accept_payload(self.e, sig, payload)
            self.assertEqual(g.accept_payload(self.e, sig, b'approved'), 'accepted_not_delivered')
        finally:
            g.db.close()

    def test_symlink_database_rejected(self):
        outside = self.root / 'outside'
        outside.write_bytes(b'unchanged')
        self.db.symlink_to(outside)
        with self.assertRaises(UnsafeStore):
            self.gate()
        self.assertEqual(outside.read_bytes(), b'unchanged')

    def test_symlink_parent_rejected(self):
        real = self.root / 'real'
        real.mkdir(mode=0o700)
        link = self.root / 'link'
        link.symlink_to(real, target_is_directory=True)
        with self.assertRaises(UnsafeStore):
            self.gate(link / 'receipts.sqlite')

    def test_traversal_and_relative_rejected(self):
        for path in ('relative.sqlite', str(self.root / '..' / self.root.name / 'x.sqlite')):
            with self.subTest(path=path), self.assertRaises(UnsafeStore):
                self.gate(path)

    def test_world_writable_parent_rejected(self):
        shared = self.root / 'shared'
        shared.mkdir(mode=0o700)
        shared.chmod(0o777)
        with self.assertRaises(UnsafeStore):
            self.gate(shared / 'receipts.sqlite')

    def test_permissive_file_and_hardlink_rejected(self):
        self.db.touch(mode=0o600)
        self.db.chmod(0o644)
        with self.assertRaises(UnsafeStore):
            self.gate()
        self.db.chmod(0o600)
        second = self.root / 'linked.sqlite'
        os.link(self.db, second)
        with self.assertRaises(UnsafeStore):
            self.gate()

    def test_threaded_concurrent_duplicate_one_winner(self):
        g = self.gate()
        sig = Gate.sign(self.e, self.key)
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
                futures = [pool.submit(_accept_thread, g, self.e, sig) for _ in range(12)]
                results = [f.result() for f in futures]
            self.assertEqual(results.count('accepted_not_delivered'), 1)
            self.assertEqual(results.count('replay'), 11)
        finally:
            g.db.close()

    def test_process_concurrent_duplicate_one_winner(self):
        sig = Gate.sign(self.e, self.key)
        with concurrent.futures.ProcessPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(_accept_in_process, [str(self.db)] * 8,
                                    [self.e] * 8, [sig] * 8))
        self.assertEqual(results.count('accepted_not_delivered'), 1)
        self.assertEqual(results.count('replay'), 7)

    def test_restart_and_no_auto_delivery(self):
        g = self.gate()
        sig = Gate.sign(self.e, self.key)
        self.assertEqual(g.accept_payload(self.e, sig, b'approved'), 'accepted_not_delivered')
        g.db.close()
        g2 = self.gate()
        try:
            with self.assertRaisesRegex(Rejected, 'replay'):
                g2.accept_payload(self.e, sig, b'approved')
            self.assertEqual(g2.db.execute('SELECT state FROM receipts').fetchone()[0], 'accepted_not_delivered')
        finally:
            g2.db.close()

    def test_malformed_action_rejected_without_type_error(self):
        g = self.gate()
        self.e['action'] = ['wake_request']
        try:
            with self.assertRaisesRegex(Rejected, 'policy'):
                g.accept(self.e, 'invalid')
        finally:
            g.db.close()


def _accept_thread(g, envelope, signature):
    try:
        return g.accept(envelope, signature)
    except Rejected as exc:
        return str(exc)


if __name__ == '__main__':
    unittest.main()
