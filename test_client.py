"""Local, reproducible CLI integration tests; no remote access required."""
import os
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from client import BatonCLI, validate_endpoint
from server import app, database


class ClientTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        db = os.path.join(self.temp.name, "test.sqlite3")
        database(db).close()
        self.http = ThreadingHTTPServer(
            ("127.0.0.1", 0),
            app(db, {"martin": "m" * 40, "ruben": "r" * 40}),
        )
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()
        url = f"http://127.0.0.1:{self.http.server_port}"
        self.martin = BatonCLI(url, "m" * 40)
        self.ruben = BatonCLI(url, "r" * 40)

    def tearDown(self):
        self.http.shutdown()
        self.http.server_close()
        self.thread.join()
        self.temp.cleanup()

    def test_two_way_with_explicit_ack(self):
        receipt = self.martin.send("ruben", "Hello Ruben", "martin-001")
        self.assertEqual(receipt["status"], "queued")
        incoming = self.ruben.inbox()["messages"]
        self.assertEqual(len(incoming), 1)
        self.assertEqual(incoming[0]["body"], "Hello Ruben")
        self.assertEqual(self.ruben.ack("martin-001")["status"], "client_acknowledged")
        self.assertEqual(self.ruben.inbox()["messages"], [])
        self.ruben.send("martin", "Hello Martin", "ruben-001")
        self.assertEqual(self.martin.inbox()["messages"][0]["body"], "Hello Martin")

    def test_inbox_does_not_ack(self):
        self.martin.send("ruben", "Unacknowledged", "not-acked")
        self.assertEqual(len(self.ruben.inbox()["messages"]), 1)
        self.assertEqual(len(self.ruben.inbox()["messages"]), 1)

    def test_remote_plain_http_rejected(self):
        with self.assertRaises(ValueError):
            validate_endpoint("http://example.com:8765")
        self.assertEqual(validate_endpoint("https://example.com/"), "https://example.com")

    def test_credentials_in_url_rejected(self):
        with self.assertRaises(ValueError):
            validate_endpoint("https://token@example.com")
        with self.assertRaises(ValueError):
            validate_endpoint("https://example.com/?token=secret")


if __name__ == "__main__":
    unittest.main()
