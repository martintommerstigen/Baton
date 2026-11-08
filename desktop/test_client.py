import pathlib
import sys
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from server import app, database
from app import BatonClient

class ClientTest(unittest.TestCase):
    def test_two_independent_users(self):
        with tempfile.TemporaryDirectory() as temp:
            db = str(pathlib.Path(temp) / "baton.sqlite3")
            database(db).close()
            http = ThreadingHTTPServer(("127.0.0.1", 0), app(db, {"alice": "a" * 40, "bob": "b" * 40}))
            thread = threading.Thread(target=http.serve_forever, daemon=True)
            thread.start()
            try:
                url = f"http://127.0.0.1:{http.server_port}"
                alice = BatonClient(url, "a" * 40)
                bob = BatonClient(url, "b" * 40)
                receipt = alice.send("bob", "Hello from Alice")
                self.assertEqual(receipt["status"], "queued")
                self.assertEqual(alice.inbox(), [])
                messages = bob.inbox()
                self.assertEqual(len(messages), 1)
                self.assertEqual(messages[0]["body"], "Hello from Alice")
                self.assertEqual(bob.acknowledge(receipt["id"])["status"], "client_acknowledged")
                self.assertEqual(bob.inbox(), [])
                self.assertEqual(bob.send("alice", "Hello back")["status"], "queued")
                self.assertEqual(alice.inbox()[0]["body"], "Hello back")
            finally:
                http.shutdown()
                http.server_close()
                thread.join()

    def test_remote_http_rejected(self):
        with self.assertRaises(ValueError):
            BatonClient("http://example.com:8765", "token")

if __name__ == "__main__":
    unittest.main()