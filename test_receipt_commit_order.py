"""Verify Baton HTTP success receipts are sent only after durable SQLite commit.

A second SQLite connection observes state at the instant the response is built.
This is a local loopback test with isolated temporary storage, not a live relay.
"""
import json
import os
import sqlite3
import tempfile
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from server import app, database


class CommitBeforeReceiptTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp.name, 'relay.sqlite3')
        database(self.db_path).close()
        base = app(self.db_path, {'alice': 'a'*40, 'bob': 'b'*40})
        db_path = self.db_path
        class AuditedHandler(base):
            observations = []
            def reply(self, code, data):
                if (code, data.get('status')) in ((202, 'queued'), (200, 'client_acknowledged')):
                    with sqlite3.connect(db_path, timeout=3) as independent:
                        row = independent.execute('SELECT read_at FROM messages WHERE id=?', (data['id'],)).fetchone()
                    self.observations.append((code, data['status'], row))
                return super().reply(code, data)
        self.handler = AuditedHandler
        self.http = ThreadingHTTPServer(('127.0.0.1', 0), AuditedHandler)
        self.worker = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.worker.start()
        self.url = 'http://127.0.0.1:' + str(self.http.server_port)

    def tearDown(self):
        self.http.shutdown()
        self.http.server_close()
        self.worker.join()
        self.tmp.cleanup()

    def request(self, actor, endpoint, payload):
        request = urllib.request.Request(
            self.url + endpoint,
            data=json.dumps(payload).encode('utf-8'),
            headers={'Authorization': 'Bearer ' + actor*40, 'Content-Type': 'application/json'},
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.load(response)

    def test_send_and_ack_committed_before_success_receipt(self):
        self.assertEqual(self.request('a', '/v1/send', {'id':'durable-1','to':'bob','body':'hello'})[0], 202)
        self.assertEqual(self.request('b', '/v1/ack', {'id':'durable-1'})[0], 200)
        self.assertEqual(len(self.handler.observations), 2)
        sent, acked = self.handler.observations
        self.assertEqual(sent[:2], (202, 'queued'))
        self.assertIsNotNone(sent[2], '202 was generated before the row was committed')
        self.assertEqual(acked[:2], (200, 'client_acknowledged'))
        self.assertIsNotNone(acked[2], '200 was generated before the row was committed')
        self.assertIsNotNone(acked[2][0], 'ACK 200 was generated before read_at was committed')


if __name__ == '__main__':
    unittest.main()

