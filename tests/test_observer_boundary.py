"""B5-RJ17 scoped isolation negatives; no browser/CDP mutations."""
import errno
import os
import socket
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from remote_security import observer_boundary as b


class BoundaryTests(unittest.TestCase):
    def test_same_network_namespace_fails_closed(self):
        if os.geteuid() == 0:
            self.skipTest('non-root process required')
        with mock.patch.object(b, '_netns', return_value=(1, 7)), \
             mock.patch.object(b.os, 'stat', return_value=type('S', (), {'st_uid': 21001})()):
            with self.assertRaisesRegex(b.BoundaryDenied, 'shares collector'):
                b.audit_observer_boundary(collector_pid=123, collector_uid=21001,
                    profile='/profile', snapshot_socket='/socket')

    def test_missing_profile_is_not_proof_of_denial(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(b.BoundaryDenied, 'not established'):
                b._profile_denied(d + '/missing')

    def test_readable_profile_denied(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(b.BoundaryDenied, 'can read'):
                b._profile_denied(d)

    def test_symlink_profile_not_accepted(self):
        with tempfile.TemporaryDirectory() as d:
            os.symlink(d, d + '/alias')
            with self.assertRaises(b.BoundaryDenied):
                b._profile_denied(d + '/alias')

    def test_path_traversal_denied(self):
        for path in ('relative', '/tmp/../etc', '/tmp//socket', '/tmp/./socket'):
            with self.subTest(path=path), self.assertRaises(b.BoundaryDenied):
                b._canonical_path(path)

    def test_live_cdp_listener_denied(self):
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            listener.listen(1)
            with self.assertRaisesRegex(b.BoundaryDenied, 'can connect'):
                b._cdp_denied('127.0.0.1', listener.getsockname()[1])

    def test_af_inet_creation_denied_by_policy(self):
        with mock.patch.object(b.socket, 'socket', side_effect=OSError(errno.EAFNOSUPPORT, 'blocked')):
            b._cdp_denied('127.0.0.1', 9222)

    def test_unlisted_cdp_host_denied(self):
        for host in ('localhost', '0.0.0.0', '192.0.2.1'):
            with self.subTest(host=host), self.assertRaises(b.BoundaryDenied):
                b._cdp_denied(host, 9222)

    def test_wrong_socket_owner_or_type_denied(self):
        with tempfile.TemporaryDirectory() as d:
            path = d + '/fake.sock'
            Path(path).write_text('not a socket')
            with self.assertRaises(b.BoundaryDenied):
                b._snapshot_peer(path, os.getuid())

    def test_snapshot_peer_uid_checked(self):
        with tempfile.TemporaryDirectory() as d:
            path = d + '/real.sock'
            with socket.socket(socket.AF_UNIX) as listener:
                listener.bind(path)
                listener.listen(1)
                with self.assertRaises(b.BoundaryDenied):
                    b._snapshot_peer(path, os.getuid() + 1)
                b._snapshot_peer(path, os.getuid())
                conn, _ = listener.accept()
                conn.close()

    def test_timeout_is_ambiguous_not_pass(self):
        class FakeSocket:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def settimeout(self, t): pass
            def connect(self, address): raise socket.timeout('no answer')
        with mock.patch.object(b.socket, 'socket', return_value=FakeSocket()):
            with self.assertRaisesRegex(b.BoundaryDenied, 'ambiguous'):
                b._cdp_denied('127.0.0.1', 9222)

    def test_scoped_success_requires_all_checks(self):
        if os.geteuid() == 0:
            self.skipTest('non-root process required')
        statinfo = type('S', (), {'st_uid': 21001, 'st_dev': 1, 'st_ino': 8})()
        with mock.patch.object(b.os, 'stat', return_value=statinfo), \
             mock.patch.object(b, '_netns', side_effect=lambda p: (1, 1) if p == '/proc/self/ns/net' else (1, 2)), \
             mock.patch.object(b, '_profile_denied'), \
             mock.patch.object(b, '_cdp_denied'), \
             mock.patch.object(b, '_snapshot_peer'):
            result = b.audit_observer_boundary(collector_pid=123, collector_uid=21001,
                profile='/profile', snapshot_socket='/socket')
        self.assertEqual(result['status'], 'scoped_preflight_pass_not_attestation')
        self.assertNotIn('verified', result['status'])


if __name__ == '__main__':
    unittest.main()
