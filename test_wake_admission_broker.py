"""B1/B5 offline admission tests. No UI, Greg or production files touched."""
import hashlib
import json
import os
from pathlib import Path
import socket
import tempfile
import threading
import unittest

from wake_admission_broker import AdmissionStore, Broker, query, pause_present_or_untrusted


class AdmissionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.pause = self.root / "PAUSE_UI_WRITES"
        self.db = self.root / "state.sqlite"
        self.sock = self.root / "broker.sock"
        self.allowed = ["chat-B", "chat-C"]
        self.store = AdmissionStore(self.db, self.pause, self.allowed)
        self.broker = Broker(self.sock, self.store, [os.getuid()])
        self.thread = threading.Thread(target=self.broker.serve_forever, kwargs={"poll_interval": .01}, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop)

    def stop(self):
        if getattr(self, "broker", None):
            self.broker.shutdown()
            self.broker.server_close()
            self.sock.unlink(missing_ok=True)
            self.broker = None

    def envelope(self, target="chat-B", message="m1"):
        return dict(op="admit", conversation_id=target, message_id=message,
                    origin_turn_id="turn-A", sender_id="chat-A",
                    payload_sha256=hashlib.sha256(b"exact payload").hexdigest())

    def ask(self, req):
        return query(self.sock, req)

    def test_health_is_not_delivery(self):
        self.assertEqual(self.ask({"op": "status"}), {"state": "ready", "outstanding": 0})
        self.assertEqual(self.ask(self.envelope())["state"], "admitted_not_delivered")
        self.assertEqual(self.ask({"op": "status"})["outstanding"], 1)

    def test_duplicate_and_changed_payload_both_blocked(self):
        req = self.envelope()
        self.assertEqual(self.ask(req)["state"], "admitted_not_delivered")
        self.assertEqual(self.ask(req)["reason"], "outstanding_attempt")
        other = self.envelope(message="m2")
        self.assertEqual(self.ask(other)["reason"], "outstanding_attempt")

    def test_two_distinct_conversations_admitted_once(self):
        self.assertEqual(self.ask(self.envelope())["state"], "admitted_not_delivered")
        self.assertEqual(self.ask(self.envelope("chat-C", "m2"))["state"], "admitted_not_delivered")

    def test_unknown_conversation_and_bad_digest(self):
        self.assertEqual(self.ask(self.envelope("chat-Z"))["reason"], "conversation_not_allowed")
        bad = self.envelope()
        bad["payload_sha256"] = "invalid"
        self.assertEqual(self.ask(bad)["reason"], "invalid_envelope")
        self.assertEqual(self.ask({"op": "execute", "command": "id"})["reason"], "unsupported_operation")

    def test_pause_marker_and_symlink_fail_closed(self):
        self.pause.write_text("pause")
        self.assertEqual(self.ask(self.envelope())["reason"], "paused_or_untrusted")
        self.pause.unlink()
        self.pause.symlink_to(self.root / "nonexistent")
        self.assertEqual(self.ask(self.envelope())["reason"], "paused_or_untrusted")

    def test_missing_parent_fails_closed(self):
        self.store.pause_path = str(self.root / "missing" / "PAUSE_UI_WRITES")
        self.assertTrue(pause_present_or_untrusted(self.store.pause_path))
        self.assertEqual(self.ask(self.envelope())["reason"], "paused_or_untrusted")

    def test_persistent_pause_is_not_revocation(self):
        self.assertEqual(self.ask(self.envelope())["state"], "admitted_not_delivered")
        self.assertEqual(self.ask({"op": "pause"})["state"], "pause_recorded_not_revocation")
        self.assertEqual(self.ask(self.envelope("chat-C"))["reason"], "paused_or_untrusted")
        self.assertEqual(self.ask({"op": "status"}), {"state": "paused", "outstanding": 1})

    def test_restart_keeps_attempt(self):
        self.assertEqual(self.ask(self.envelope())["state"], "admitted_not_delivered")
        self.stop()
        self.store = AdmissionStore(self.db, self.pause, self.allowed)
        self.broker = Broker(self.sock, self.store, [os.getuid()])
        self.thread = threading.Thread(target=self.broker.serve_forever, kwargs={"poll_interval": .01}, daemon=True)
        self.thread.start()
        self.assertEqual(self.ask(self.envelope())["reason"], "outstanding_attempt")

    def test_concurrent_admissions_only_one(self):
        barrier = threading.Barrier(6)
        answers = []
        lock = threading.Lock()
        def worker():
            barrier.wait()
            result = self.ask(self.envelope())
            with lock:
                answers.append(result["state"])
        threads = [threading.Thread(target=worker) for _ in range(6)]
        for t in threads: t.start()
        for t in threads: t.join()
        self.assertEqual(answers.count("admitted_not_delivered"), 1)
        self.assertEqual(answers.count("rejected"), 5)

    def test_peer_uid_denied(self):
        self.stop()
        self.broker = Broker(self.sock, self.store, [os.getuid() + 100000])
        self.thread = threading.Thread(target=self.broker.serve_forever, kwargs={"poll_interval": .01}, daemon=True)
        self.thread.start()
        with self.assertRaises(RuntimeError):
            self.ask({"op": "status"})

    def test_oversized_request_is_ignored(self):
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.connect(str(self.sock))
            s.sendall(b"x" * 9000 + b"\n")
            s.shutdown(socket.SHUT_WR)
            self.assertEqual(s.recv(128), b"")
        self.assertEqual(self.ask({"op": "status"})["state"], "ready")

    def test_existing_socket_is_not_replaced(self):
        with self.assertRaises(OSError):
            Broker(self.sock, self.store, [os.getuid()])


if __name__ == "__main__":
    unittest.main()
