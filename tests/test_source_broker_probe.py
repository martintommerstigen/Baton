"""Negative and no-contact tests for the B5 source broker readiness probe."""
import os
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

from remote_security.source_broker_probe import probe, ProbeUncertain, UntrustedBroker


@unittest.skipUnless(os.name == 'posix' and hasattr(socket, 'SO_PEERCRED'), 'Linux only')
class ProbeTests(unittest.TestCase):
    def setUp(self):
        if os.geteuid() == 0:
            self.skipTest('non-root local fixture')
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.base.chmod(0o710)
        self.path = self.base / 'broker.sock'
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.addCleanup(self.sock.close)
        self.sock.bind(str(self.path))
        self.path.chmod(0o660)
        self.sock.listen(2)
        self.uid = os.geteuid()

    def test_same_uid_cannot_be_claimed_as_secure_broker(self):
        with self.assertRaises(UntrustedBroker):
            probe(str(self.path), self.uid)

    def test_wrong_uid_fails_without_connecting(self):
        with patch('remote_security.source_broker_probe.socket.socket', side_effect=AssertionError('connected')):
            with self.assertRaises(UntrustedBroker):
                probe(str(self.path), self.uid + 1)

    def test_symlinked_socket_is_rejected(self):
        link = self.base / 'alias.sock'
        link.symlink_to(self.path)
        with self.assertRaises(UntrustedBroker):
            probe(str(link), self.uid + 1)

    def test_parent_symlink_is_rejected(self):
        alias = self.base.parent / ('alias-' + self.base.name)
        alias.symlink_to(self.base, target_is_directory=True)
        self.addCleanup(alias.unlink)
        with self.assertRaises(UntrustedBroker):
            probe(str(alias / 'broker.sock'), self.uid + 1)

    def test_world_writable_socket_rejected(self):
        self.path.chmod(0o662)
        with self.assertRaises(UntrustedBroker):
            probe(str(self.path), self.uid + 1)

    def test_missing_socket_fails_closed(self):
        self.path.unlink()
        with self.assertRaises((UntrustedBroker, ProbeUncertain)):
            probe(str(self.path), self.uid + 1)

    def test_invalid_timeout_and_flags(self):
        for t in (0, 3, float('nan')):
            with self.subTest(timeout=t), self.assertRaises(ValueError):
                probe(str(self.path), self.uid + 1, timeout=t)
        with self.assertRaises(ValueError):
            probe(str(self.path), self.uid + 1, connect=1)


if __name__ == '__main__':
    unittest.main()
