import hashlib
import tempfile
import time
import unittest
from pathlib import Path
from remote_security.envelope_gate import Gate, Rejected

class GateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.tmp.name) / "receipts.sqlite")
        self.key = b"k" * 32
        self.g = Gate(self.path, {"sender000": self.key}, {"sender000"}, {"target000"})
        self.e = dict(version=1, sender="sender000", target="target000", message_id="message000", issued_at=int(time.time()), action="wake_request", payload_sha256=hashlib.sha256(b"approved").hexdigest())
    def tearDown(self):
        self.g.db.close()
        self.tmp.cleanup()
    def signed(self, e=None, key=None):
        e = e or self.e
        return self.g.accept(e, Gate.sign(e, key or self.key))
    def test_replay_and_restart(self):
        self.assertEqual(self.signed(), "accepted_not_delivered")
        self.g.db.close()
        self.g = Gate(self.path, {"sender000": self.key}, {"sender000"}, {"target000"})
        with self.assertRaisesRegex(Rejected, "replay"):
            self.signed()
    def test_forgery(self):
        with self.assertRaisesRegex(Rejected, "signature"):
            self.signed(key=b"x"*32)
    def test_tamper(self):
        sig = Gate.sign(self.e, self.key)
        self.e["target"] = "target001"
        with self.assertRaisesRegex(Rejected, "policy"):
            self.g.accept(self.e, sig)
    def test_expired(self):
        self.e["issued_at"] -= 120
        with self.assertRaisesRegex(Rejected, "expired"):
            self.signed()
    def test_collision(self):
        self.signed()
        self.e["payload_sha256"] = hashlib.sha256(b"different").hexdigest()
        with self.assertRaisesRegex(Rejected, "collision"):
            self.signed()
    def test_path_not_a_command(self):
        self.e["action"] = "../../bin/sh"
        with self.assertRaisesRegex(Rejected, "policy"):
            self.signed()
    def test_double_send_different_connections(self):
        second = Gate(self.path, {"sender000": self.key}, {"sender000"}, {"target000"})
        try:
            self.signed()
            with self.assertRaisesRegex(Rejected, "replay"):
                second.accept(self.e, Gate.sign(self.e, self.key))
        finally:
            second.db.close()
    def test_unknown_sender(self):
        self.e["sender"] = "other000"
        with self.assertRaisesRegex(Rejected, "policy"):
            self.signed()
if __name__ == "__main__":
    unittest.main()
