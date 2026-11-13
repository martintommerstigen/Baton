"""B5 Linux peer-auth negatives, isolated AF_UNIX; no Greg or UI writes."""
import os
from pathlib import Path
import socket
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from remote_security.broker_peer import (BrokerUncertain, UntrustedBroker,
                                         query_verified_broker)


@unittest.skipUnless(hasattr(socket, 'SO_PEERCRED'), 'Linux SO_PEERCRED required')
@unittest.skipIf(os.getuid() == 0, 'client peer tests require unprivileged UID')
class BrokerPeerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.root.chmod(0o700)
        self.path = self.root / 'broker.sock'
        self.uid = os.getuid()
        self.request = {'op': 'status'}

    def serve(self, reply=b'{"state":"ready"}\n'):
        server = socket.socket(socket.AF_UNIX)
        server.bind(str(self.path))
        os.chmod(self.path, 0o600)
        server.listen(1)
        seen = []
        def run():
            try:
                server.settimeout(2)
                conn, _ = server.accept()
                with conn:
                    conn.settimeout(1)
                    try:
                        data = conn.recv(8193)
                        seen.append(data)
                        if data:
                            conn.sendall(reply)
                    except OSError:
                        pass
            except OSError:
                pass
            finally:
                server.close()
        worker = threading.Thread(target=run, daemon=True)
        worker.start()
        self.addCleanup(worker.join, 2)
        return seen

    def test_valid_cooperative_test_mode_is_not_claimed_isolated(self):
        seen = self.serve()
        self.assertEqual(query_verified_broker(self.path, self.uid, self.request,
                         require_distinct_uid=False), {'state':'ready'})
        self.assertEqual(seen, [b'{"op":"status"}\n'])

    def test_same_uid_is_rejected_by_default_before_send(self):
        self.serve()
        with self.assertRaises(UntrustedBroker):
            query_verified_broker(self.path, self.uid, self.request)

    def test_forged_peer_uid_never_receives_payload(self):
        seen = self.serve()
        with self.assertRaises(UntrustedBroker):
            query_verified_broker(self.path, self.uid + 1, self.request)
        # EOF (b'') is permitted; nonempty request bytes are not.
        self.assertFalse(any(seen), 'peer saw nonempty request bytes')

    def test_connected_peer_credentials_checked_before_disclosure(self):
        seen = self.serve()
        # Simulate a pathname metadata pass after an endpoint swap.
        # The connected peer's kernel UID still determines whether bytes leave.
        from remote_security import broker_peer
        with patch.object(broker_peer, '_checked_socket_path', return_value=self.path):
            with self.assertRaises(UntrustedBroker):
                query_verified_broker(self.path, self.uid + 1, self.request)
        # EOF (b'') is permitted; nonempty request bytes are not.
        self.assertFalse(any(seen), 'peer saw nonempty request bytes')

    def test_path_symlink_rejected(self):
        self.serve()
        link = self.root / 'alias.sock'
        link.symlink_to(self.path)
        with self.assertRaises(UntrustedBroker):
            query_verified_broker(link, self.uid, self.request, require_distinct_uid=False)

    def test_parent_symlink_rejected(self):
        self.serve()
        link = self.root / 'alias'
        link.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(UntrustedBroker):
            query_verified_broker(link / 'broker.sock', self.uid, self.request,
                                  require_distinct_uid=False)

    def test_shared_writable_parent_rejected(self):
        self.serve()
        self.root.chmod(0o777)
        with self.assertRaises(UntrustedBroker):
            query_verified_broker(self.path, self.uid, self.request, require_distinct_uid=False)

    def test_regular_file_rejected(self):
        self.path.write_text('not socket')
        with self.assertRaises(UntrustedBroker):
            query_verified_broker(self.path, self.uid, self.request, require_distinct_uid=False)

    def test_ambiguous_response_never_authorizes(self):
        self.serve(b'{"state":"ready"}\n{"state":"ready"}\n')
        with self.assertRaises(BrokerUncertain):
            query_verified_broker(self.path, self.uid, self.request, require_distinct_uid=False)

    def test_duplicate_json_keys_never_authorize(self):
        self.serve(b'{"state":"ready","state":"click_started_uncertain"}\n')
        with self.assertRaises(BrokerUncertain):
            query_verified_broker(self.path, self.uid, self.request, require_distinct_uid=False)

    def test_empty_response_is_uncertain_not_retryable(self):
        self.serve(b'')
        with self.assertRaises(BrokerUncertain):
            query_verified_broker(self.path, self.uid, self.request, require_distinct_uid=False)

    def test_oversized_reply_rejected(self):
        self.serve(b'{"state":"' + b'x'*8200 + b'"}\n')
        with self.assertRaises(BrokerUncertain):
            query_verified_broker(self.path, self.uid, self.request, require_distinct_uid=False)

    def test_oversized_request_rejected_before_connect(self):
        self.serve()
        with self.assertRaises(ValueError):
            query_verified_broker(self.path, self.uid, {'op':'x'*8192},
                                  require_distinct_uid=False)

    def test_root_broker_uid_rejected(self):
        self.serve()
        with self.assertRaises(ValueError):
            query_verified_broker(self.path, 0, self.request)

    def test_slow_trickle_reply_has_absolute_deadline(self):
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(str(self.path))
        os.chmod(self.path, 0o600)
        server.listen(1)
        def trickle():
            try:
                server.settimeout(2)
                conn, _ = server.accept()
                with conn:
                    conn.settimeout(1)
                    conn.recv(8193)
                    for _ in range(18):
                        try:
                            conn.sendall(b" ")
                        except OSError:
                            break
                        time.sleep(0.05)
            except OSError:
                pass
            finally:
                server.close()
        worker = threading.Thread(target=trickle, daemon=True)
        worker.start()
        start = time.monotonic()
        with self.assertRaises(BrokerUncertain):
            query_verified_broker(self.path, self.uid, self.request,
                                  timeout=0.20, require_distinct_uid=False)
        self.assertLess(time.monotonic() - start, 0.60,
                        "slow reply must not reset total timeout")
        worker.join(2)
        self.assertFalse(worker.is_alive())

    def test_unbounded_timeout_rejected(self):
        self.serve()
        for value in (None, 0, -1, float('inf'), float('nan'), 100):
            with self.subTest(value=value), self.assertRaises(ValueError):
                query_verified_broker(self.path, self.uid, self.request,
                                      timeout=value, require_distinct_uid=False)

    def test_path_traversal_rejected(self):
        self.serve()
        with self.assertRaises(UntrustedBroker):
            query_verified_broker(str(self.root / '..' / self.root.name / 'broker.sock'),
                                  self.uid, self.request, require_distinct_uid=False)

if __name__ == '__main__':
    unittest.main()
