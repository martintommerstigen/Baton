"""B5 R18: read-only manifest, non-authoritative pause and provenance gates."""
import os
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

from remote_security import host_manifest as hm


class HostManifestTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.root.chmod(0o700)
        self.pause = self.root / 'PAUSE_UI_WRITES'

    def test_default_does_not_connect_or_authorize(self):
        endpoint = {'state': 'endpoint_metadata_only', 'peer_uid_verified': False,
                    'request_bytes_sent': 0}
        with patch.object(hm, 'probe', return_value=endpoint) as mock, patch.object(hm, '_socket_metadata', return_value={'inode': 123}):
            result = hm.manifest('/private/socket', 21001, pause_path=self.pause)
        mock.assert_called_once_with('/private/socket', 21001, connect=False)
        self.assertEqual(result['pause_marker'], 'absent_at_checked_path_not_authorization')
        self.assertEqual(result['pause_authorization'], 'never_inferred')
        self.assertEqual(result['ui_write'], 'not_attempted')
        self.assertEqual(result['greg_live'], 'not_established')
        self.assertEqual(len(result['source_file_sha256_not_runtime_attestation']), 3)
        self.assertNotIn(str(self.root), str(result))

    def test_present_pause_is_observed_without_reading_contents(self):
        self.pause.write_text('private text never to be read')
        with patch.object(hm, 'probe', return_value={'state': 'endpoint_metadata_only'}), patch.object(hm, '_socket_metadata', return_value={'inode': 123}):
            result = hm.manifest('/private/socket', 21001, pause_path=self.pause)
        self.assertEqual(result['pause_marker'], 'present_at_checked_path')
        self.assertNotIn('private text', str(result))

    def test_opt_in_contact_once_no_retries(self):
        with patch.object(hm, 'probe', return_value={'state': 'kernel_peer_uid_verified_no_request'}) as mock, patch.object(hm, '_socket_metadata', return_value={'inode': 123}):
            result = hm.manifest('/private/socket', 21001, connect=True)
        mock.assert_called_once_with('/private/socket', 21001, connect=True)
        self.assertEqual(result['socket_observation']['state'], 'kernel_peer_uid_verified_no_request')
        self.assertFalse(result['automatic_retry'])

    def test_uncertain_peer_is_not_retried(self):
        with patch.object(hm, 'probe', side_effect=hm.ProbeUncertain('uncertain')) as mock:
            with self.assertRaises(hm.ProbeUncertain):
                hm.manifest('/private/socket', 21001, connect=True)
        self.assertEqual(mock.call_count, 1)

    def test_symlink_pause_and_hardlink_rejected(self):
        real = self.root / 'real'
        real.write_text('x')
        self.pause.symlink_to(real)
        with self.assertRaises(hm.ManifestUncertain):
            hm.pause_marker(self.pause)
        self.pause.unlink()
        os.link(real, self.pause)
        with self.assertRaises(hm.ManifestUncertain):
            hm.pause_marker(self.pause)

    def test_symlink_parent_and_traversal_rejected(self):
        sub = self.root / 'sub'
        sub.mkdir()
        alias = self.root / 'alias'
        alias.symlink_to(sub, target_is_directory=True)
        with self.assertRaises(hm.ManifestUncertain):
            hm.pause_marker(alias / 'PAUSE_UI_WRITES')
        for path in ('/tmp/../bad', '/tmp//bad', 'relative/path'):
            with self.subTest(path=path), self.assertRaises(hm.ManifestUncertain):
                hm.pause_marker(path)

    def test_fifo_and_mutable_parent_rejected(self):
        os.mkfifo(self.pause)
        with self.assertRaises(hm.ManifestUncertain):
            hm.pause_marker(self.pause)
        self.pause.unlink()
        self.root.chmod(0o777)
        with self.assertRaises(hm.ManifestUncertain):
            hm.pause_marker(self.pause)

    def test_source_digest_rejects_symlink_and_hardlink(self):
        real = self.root / 'module.py'
        real.write_text('x=1\n')
        link = self.root / 'link.py'
        link.symlink_to(real)
        with self.assertRaises(hm.ManifestUncertain):
            hm._source_file_digest(link)
        link.unlink()
        os.link(real, link)
        with self.assertRaises(hm.ManifestUncertain):
            hm._source_file_digest(real)

    def test_source_digest_detects_path_swap_during_read(self):
        path = self.root / 'module.py'
        path.write_bytes(b'original')
        actual_read = os.read
        switched = False
        def swap_after_read(fd, count):
            nonlocal switched
            block = actual_read(fd, count)
            if not switched:
                switched = True
                path.unlink()
                path.write_bytes(b'forged')
            return block
        with patch.object(hm.os, 'read', side_effect=swap_after_read):
            with self.assertRaises(hm.ManifestUncertain):
                hm._source_file_digest(path)
        self.assertTrue(switched)

    def test_socket_inode_snapshot_and_replacement_rejected(self):
        path = self.root / 'source.sock'
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
            server.bind(str(path))
            path.chmod(0o660)
            result = hm._socket_metadata(str(path), os.geteuid())
            self.assertEqual(result['inode'], path.lstat().st_ino)
            self.assertEqual(result['scope'], 'post_probe_path_snapshot_not_atomic')
            path.unlink()
            path.write_text('replaced')
            with self.assertRaises(hm.ManifestUncertain):
                hm._socket_metadata(str(path), os.geteuid())

    def test_invalid_connect_flag_rejected_before_probe(self):
        with patch.object(hm, 'probe', side_effect=AssertionError('called')):
            with self.assertRaises(ValueError):
                hm.manifest('/private/socket', 21001, connect=1)


if __name__ == '__main__':
    unittest.main()
