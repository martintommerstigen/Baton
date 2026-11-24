"""B5 fault injection: a committed HTTP admission can have no response.

No UI writes, no retries, and no assumption that absence proves non-delivery.
"""
import hashlib
import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path

from remote_security.envelope_gate import Gate, Rejected
from remote_security.http_client import DeliveryUncertain, send_once
from remote_security.http_ingress import IngressHandler, IngressServer
from remote_security.receipt_audit import audit_receipt


class DropCommittedResponse(IngressHandler):
    def _reply(self, code, state):
        if code == 202:
            # Gate.accept_payload has already committed its SQLite transaction.
            # Simulate connection loss before a client can read the HTTP receipt.
            try:
                self.connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            self.close_connection = True
            return
        return super()._reply(code, state)


class RejectBeforeCommitGate(Gate):
    def accept_payload(self, envelope, signature, payload):
        raise Rejected('injected precommit failure')


class UncertainAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.path = str(self.root / 'receipts.sqlite')
        self.key = b'K' * 48
        self.token = b'T' * 48
        self.payload = b'harmless marker'
        self.envelope = dict(version=1, sender='sender000', target='target000',
                             message_id='message000', issued_at=int(time.time()),
                             action='wake_request',
                             payload_sha256=hashlib.sha256(self.payload).hexdigest())
        self.gate = None
        self.server = None
        self.thread = None

    def tearDown(self):
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            self.thread.join(timeout=3)
        if self.gate:
            self.gate.db.close()
        self.tmp.cleanup()

    def start(self, gate_type=Gate, handler=DropCommittedResponse):
        self.gate = gate_type(self.path, {'sender000': self.key},
                              {'sender000'}, {'target000'})
        self.server = IngressServer(0, self.token, self.gate)
        self.server.RequestHandlerClass = handler
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return 'http://127.0.0.1:%d' % self.server.server_port

    def test_commit_then_connection_drop_is_uncertain_but_auditable(self):
        url = self.start()
        with self.assertRaises(DeliveryUncertain):
            send_once(url, self.token, self.key, self.envelope, self.payload)
        self.assertEqual(self.gate.db.execute('SELECT COUNT(*) FROM receipts').fetchone()[0], 1)
        self.assertEqual(audit_receipt(self.path, 'sender000', 'message000', self.key),
                         {'classification': 'present_authenticated_payload',
                          'admission_state': 'accepted_not_delivered', 'send_permitted': False})
        # The client did not retry. A deliberate second call is rejected as replay.
        with self.assertRaises(DeliveryUncertain):
            send_once(url, self.token, self.key, self.envelope, self.payload)
        self.assertEqual(self.gate.db.execute('SELECT COUNT(*) FROM receipts').fetchone()[0], 1)

    def test_precommit_rejection_is_still_not_a_retry_permit(self):
        url = self.start(gate_type=RejectBeforeCommitGate, handler=IngressHandler)
        with self.assertRaises(DeliveryUncertain):
            send_once(url, self.token, self.key, self.envelope, self.payload)
        self.assertEqual(self.gate.db.execute('SELECT COUNT(*) FROM receipts').fetchone()[0], 0)
        self.assertEqual(audit_receipt(self.path, 'sender000', 'message000', self.key),
                         {'classification': 'absent_unknown', 'send_permitted': False})


if __name__ == '__main__':
    unittest.main()
