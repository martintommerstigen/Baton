"""Security and protocol regression tests for Baton v0.

Run: python3 -m unittest -v test_security.py
No remote machine or external network required.
"""
import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from server import app, database


class SecurityTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp.name, "messages.sqlite3")
        database(self.db_path).close()
        self.http = ThreadingHTTPServer(
            ("127.0.0.1", 0),
            app(self.db_path, {"martin": "m" * 40, "ruben": "r" * 40}),
        )
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.http.server_port}"

    def tearDown(self):
        self.http.shutdown()
        self.http.server_close()
        self.thread.join()
        self.tmp.cleanup()

    def request(self, method, path, identity=None, payload=None, headers=None):
        h = dict(headers or {})
        if identity is not None:
            h["Authorization"] = "Bearer " + identity * 40
        if payload is not None:
            h["Content-Type"] = "application/json"
        body = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(
            self.base + path, data=body, headers=h, method=method
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status, json.load(resp)
        except urllib.error.HTTPError as exc:
            return exc.code, json.load(exc)

    def test_inbox_requires_authentication(self):
        self.assertEqual(self.request("GET", "/v1/inbox")[0], 401)
        self.assertEqual(
            self.request("GET", "/v1/inbox", headers={"Authorization": "Bearer wrong"})[0],
            401,
        )

    def test_send_requires_authentication(self):
        msg = {"id": "unauthorized", "to": "ruben", "body": "Hello"}
        self.assertEqual(self.request("POST", "/v1/send", payload=msg)[0], 401)
        self.assertEqual(self.request("GET", "/v1/inbox", "r")[1]["messages"], [])

    def test_recipient_isolation_and_ack_ownership(self):
        msg = {"id": "isolation", "to": "ruben", "body": "Private"}
        self.assertEqual(self.request("POST", "/v1/send", "m", msg)[0], 202)
        self.assertEqual(self.request("GET", "/v1/inbox", "m")[1]["messages"], [])
        self.assertEqual(self.request("POST", "/v1/ack", "m", {"id": "isolation"})[0], 404)
        self.assertEqual(
            self.request("GET", "/v1/inbox", "r")[1]["messages"][0]["body"], "Private"
        )
        self.assertEqual(self.request("POST", "/v1/ack", "r", {"id": "isolation"})[0], 200)

    def test_id_conflict_across_senders(self):
        first = {"id": "shared-id", "to": "ruben", "body": "Original"}
        self.assertEqual(self.request("POST", "/v1/send", "m", first)[0], 202)
        self.assertEqual(
            self.request("POST", "/v1/send", "r", {"id": "shared-id", "to": "martin", "body": "Other"})[0],
            409,
        )

    def test_rejected_oversize_message(self):
        self.assertEqual(
            self.request("POST", "/v1/send", "m", {"id": "big", "to": "ruben", "body": "X" * 8001})[0],
            400,
        )

    def test_ack_is_not_proof_of_processing(self):
        self.assertEqual(
            self.request("POST", "/v1/send", "m", {"id": "ack-only", "to": "ruben", "body": "Unprocessed"})[1]["status"],
            "queued",
        )
        # A client may ACK without fetching or processing the message.
        self.assertEqual(
            self.request("POST", "/v1/ack", "r", {"id": "ack-only"})[1]["status"],
            "client_acknowledged",
        )
        self.assertEqual(self.request("GET", "/v1/inbox", "r")[1]["messages"], [])


if __name__ == "__main__":
    unittest.main()
