"""B5 process-crash fault injection at SQLite COMMIT / HTTP response boundary.

Kills a disposable child process, never the test runner or Greg. It tests
durable admission and restart independently of a synthetic handler that only
drops a response. A missing record is UNKNOWN, not retry authorization.
"""
import hashlib
import multiprocessing
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest

from remote_security.envelope_gate import Gate, Rejected
from remote_security.http_client import DeliveryUncertain, send_once
from remote_security.http_ingress import IngressServer
from remote_security.receipt_audit import audit_receipt


class _CrashConnection:
    """Fault-injection proxy; all production Gate SQL is still executed."""

    def __init__(self, real, phase):
        self.real = real
        self.phase = phase

    def execute(self, statement, *args):
        if statement.strip().upper() == 'COMMIT':
            if self.phase == 'before':
                os._exit(71)
            result = self.real.execute(statement, *args)
            os._exit(72)  # SQLite COMMIT succeeded, no HTTP response emitted.
        return self.real.execute(statement, *args)

    def __getattr__(self, name):
        return getattr(self.real, name)


def _serve_until_crash(database, key, token, phase, pipe):
    # Gate schema initialization must finish before we inject a fault into
    # only the per-request connection. No forked threads or inherited sockets.
    gate = Gate(database, {'sender000': key}, {'sender000'}, {'target000'})
    import remote_security.envelope_gate as envelope_module
    real_connect = envelope_module.connect_private

    def injected_connect(path):
        return _CrashConnection(real_connect(path), phase)

    envelope_module.connect_private = injected_connect
    with IngressServer(0, token, gate) as server:
        pipe.send(server.server_port)
        pipe.close()
        # ThreadingHTTPServer.handle_request() only spawns a handler thread
        # and returns immediately. Keep the parent loop alive so the handler
        # reaches the actual SQLite COMMIT before the injected process death.
        server.serve_forever(poll_interval=0.01)
    # The expected path is os._exit in the request thread.
    os._exit(73)


@unittest.skipUnless('fork' in multiprocessing.get_all_start_methods(),
                     'requires Linux fork and process crash isolation')
class ProcessCrashTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.database = str(Path(self.tmp.name) / 'receipts.sqlite')
        self.key = b'K' * 48
        self.token = b'T' * 48
        self.payload = b'harmless marker'
        self.envelope = dict(
            version=1, sender='sender000', target='target000',
            message_id='message000', issued_at=int(time.time()),
            action='wake_request',
            payload_sha256=hashlib.sha256(self.payload).hexdigest(),
        )

    def tearDown(self):
        self.tmp.cleanup()

    def crash_once(self, phase):
        context = multiprocessing.get_context('fork')
        reader, writer = context.Pipe(duplex=False)
        proc = context.Process(target=_serve_until_crash,
                               args=(self.database, self.key, self.token, phase, writer))
        proc.start()
        writer.close()
        try:
            self.assertTrue(reader.poll(5), 'child failed to bind before request')
            port = reader.recv()
            with self.assertRaises(DeliveryUncertain):
                send_once('http://127.0.0.1:%d' % port, self.token,
                          self.key, self.envelope, self.payload)
            proc.join(timeout=5)
            self.assertFalse(proc.is_alive(), 'child did not crash at COMMIT')
            self.assertEqual(proc.exitcode, 71 if phase == 'before' else 72)
            return port
        finally:
            reader.close()
            if proc.is_alive():
                proc.terminate()
                proc.join(timeout=5)
            proc.close()

    def test_process_death_after_commit_preserves_one_admission(self):
        port = self.crash_once('after')
        self.assertEqual(
            audit_receipt(self.database, 'sender000', 'message000', self.key),
            {'classification': 'present_authenticated_payload',
             'admission_state': 'accepted_not_delivered', 'send_permitted': False},
        )
        # A fresh server process-equivalent instance binds the same endpoint.
        # Explicit duplicate submission fails: restart does not erase replay.
        gate = Gate(self.database, {'sender000': self.key},
                    {'sender000'}, {'target000'})
        server = IngressServer(port, self.token, gate)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            with self.assertRaises(DeliveryUncertain):
                send_once('http://127.0.0.1:%d' % port, self.token,
                          self.key, self.envelope, self.payload)
            self.assertEqual(gate.db.execute('SELECT COUNT(*) FROM receipts').fetchone()[0], 1)
            self.assertEqual(gate.db.execute('SELECT COUNT(*) FROM payloads').fetchone()[0], 1)
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=5)
            gate.db.close()

    def test_process_death_before_commit_rolls_back_but_does_not_permit_retry(self):
        self.crash_once('before')
        self.assertEqual(
            audit_receipt(self.database, 'sender000', 'message000', self.key),
            {'classification': 'absent_unknown', 'send_permitted': False},
        )
        gate = Gate(self.database, {'sender000': self.key},
                    {'sender000'}, {'target000'})
        try:
            self.assertEqual(gate.db.execute('SELECT COUNT(*) FROM receipts').fetchone()[0], 0)
            self.assertEqual(gate.db.execute('SELECT COUNT(*) FROM payloads').fetchone()[0], 0)
        finally:
            gate.db.close()


if __name__ == '__main__':
    unittest.main()
