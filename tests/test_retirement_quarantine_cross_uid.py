"""Trusted-push only Linux kernel UID test; synthetic UI receipt, no browser."""
import hashlib
import os
from pathlib import Path
import socket
import tempfile
import unittest
from remote_security.retirement_quarantine import Quarantine, kernel_peer_uid


@unittest.skipUnless(os.name == 'posix' and hasattr(os, 'setuid') and os.geteuid() == 0 and hasattr(socket, 'SO_PEERCRED'),
                     'requires isolated privileged Linux runner')
class KernelAttestorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.root.chmod(0o711)  # Test clients may traverse only; never read broker DB.
        self.private = self.root / 'private'
        self.private.mkdir(mode=0o700)
        self.q = Quarantine(str(self.private / 'q.sqlite'))
        self.admission = dict(conversation_id='chat-B', message_id='m1', origin_turn_id='turn-A',
                              sender_id='chat-A', payload_sha256=hashlib.sha256(b'approved').hexdigest(), state='uncertain')
        self.receipt = dict(self.admission, state='verified', observed_user_turn_id='turn-B-user',
                            observed_assistant_turn_id='turn-B-assistant')

    def connect_as(self, uid):
        path = str(self.root / 'attestor.sock')
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(path)
        os.chmod(path, 0o777)  # Deliberate test: credentials, not socket mode, decide.
        listener.listen(1)
        pid = os.fork()
        if pid == 0:
            try:
                os.setgroups([])
                os.setgid(uid)
                os.setuid(uid)
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as c:
                    c.connect(path)
                    c.sendall(b'probe')
                os._exit(0)
            except BaseException:
                os._exit(1)
        try:
            conn, _ = listener.accept()
            with conn:
                self.assertEqual(conn.recv(5), b'probe')
                actual = kernel_peer_uid(conn)
                decision = self.q.record_from_socket(conn, self.admission, self.receipt, trusted_attestor_uid=20002)
        finally:
            listener.close()
            os.waitpid(pid, 0)
            os.unlink(path)
        return actual, decision

    def test_trusted_uid_candidate_not_retirement(self):
        uid, decision = self.connect_as(20002)
        self.assertEqual(uid, 20002)
        self.assertEqual(decision, 'candidate_quarantined_not_retired')
        self.assertEqual(self.q.status('chat-B')['state'], 'quarantined_not_retired')

    def test_forged_sender_from_wrong_uid_denied(self):
        uid, decision = self.connect_as(20003)
        self.assertEqual(uid, 20003)
        self.assertEqual(decision, 'reject_untrusted_attestor')
        self.assertIsNone(self.q.status('chat-B'))


if __name__ == '__main__':
    unittest.main()
