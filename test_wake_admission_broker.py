"""B1/B5 offline admission tests. No UI, Greg or production files touched."""
import hashlib
import json
import os
from pathlib import Path
import socket
import tempfile
import threading
import time
import unittest
from unittest import mock

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

    def test_negative_claimed_b_to_c_without_observed_b_turn(self):
        """NEG: kernel UID admission does not prove asserted ChatGPT source."""
        req = self.envelope("chat-C", "claimed-B-to-C")
        req["sender_id"] = "chat-B"
        req["origin_turn_id"] = "unverified-B-turn"
        self.assertEqual(self.ask(req)["state"], "admitted_not_delivered")
        # A forged source claim must not be promoted to a verified wake.
        self.assertEqual(self.ask({"op": "status"})["outstanding"], 1)

    def test_symlinked_pause_parent_fails_closed(self):
        target = self.root / "real"
        target.mkdir()
        link = self.root / "link"
        link.symlink_to(target, target_is_directory=True)
        self.store.pause_path = str(link / "PAUSE_UI_WRITES")
        self.assertEqual(self.ask(self.envelope())["reason"], "paused_or_untrusted")

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
        # A denied kernel UID may cause EOF or ECONNRESET depending on timing.
        with self.assertRaises((RuntimeError, OSError)):
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


    def test_begin_click_requires_prior_admission(self):
        req = self.envelope()
        req["op"] = "begin_click"
        self.assertEqual(self.ask(req), {"state": "rejected", "reason": "no_admission"})
        self.assertEqual(self.ask({"op": "status"})["outstanding"], 0)

    def test_begin_click_binds_exact_envelope(self):
        original = self.envelope()
        self.assertEqual(self.ask(original)["state"], "admitted_not_delivered")
        for field, wrong in (("message_id", "m2"), ("sender_id", "chat-B"),
                             ("origin_turn_id", "different-turn"),
                             ("payload_sha256", hashlib.sha256(b"changed").hexdigest())):
            req = dict(original, op="begin_click")
            req[field] = wrong
            self.assertEqual(self.ask(req)["reason"], "envelope_mismatch_or_attempt_closed")
        self.assertEqual(self.ask(dict(original, op="begin_click"))["state"], "click_started_uncertain")

    def test_begin_click_is_one_way_and_no_second_send(self):
        req = self.envelope()
        self.assertEqual(self.ask(req)["state"], "admitted_not_delivered")
        begin = dict(req, op="begin_click")
        self.assertEqual(self.ask(begin)["state"], "click_started_uncertain")
        self.assertEqual(self.ask(begin)["reason"], "envelope_mismatch_or_attempt_closed")
        self.assertEqual(self.ask(req)["reason"], "outstanding_attempt")
        self.assertEqual(self.ask(self.envelope(message="another"))["reason"], "outstanding_attempt")

    def test_click_started_persists_across_broker_restart(self):
        req = self.envelope()
        self.ask(req)
        self.assertEqual(self.ask(dict(req, op="begin_click"))["state"], "click_started_uncertain")
        self.stop()
        self.store = AdmissionStore(self.db, self.pause, self.allowed)
        self.broker = Broker(self.sock, self.store, [os.getuid()])
        self.thread = threading.Thread(target=self.broker.serve_forever, kwargs={"poll_interval": .01}, daemon=True)
        self.thread.start()
        self.assertEqual(self.ask(dict(req, op="begin_click"))["reason"],
                         "envelope_mismatch_or_attempt_closed")
        self.assertEqual(self.ask(req)["reason"], "outstanding_attempt")

    def test_pause_before_begin_click_blocks_transition(self):
        req = self.envelope()
        self.ask(req)
        self.assertEqual(self.ask({"op": "pause"})["state"], "pause_recorded_not_revocation")
        self.assertEqual(self.ask(dict(req, op="begin_click"))["reason"], "paused_or_untrusted")
        db = self.store.connect()
        try:
            self.assertEqual(db.execute("SELECT state FROM admissions").fetchone()[0], "admitted")
        finally:
            db.close()

    def test_concurrent_begin_click_only_one_transition(self):
        req = self.envelope()
        self.ask(req)
        begin = dict(req, op="begin_click")
        barrier = threading.Barrier(5)
        states = []
        lock = threading.Lock()
        def worker():
            barrier.wait()
            response = self.ask(begin)
            with lock:
                states.append(response["state"])
        workers = [threading.Thread(target=worker) for _ in range(5)]
        for worker_thread in workers:
            worker_thread.start()
        for worker_thread in workers:
            worker_thread.join()
        self.assertEqual(states.count("click_started_uncertain"), 1)
        self.assertEqual(states.count("rejected"), 4)

    def test_pause_after_begin_click_cannot_revoke_uncertainty(self):
        req = self.envelope()
        self.ask(req)
        self.assertEqual(self.ask(dict(req, op="begin_click"))["state"], "click_started_uncertain")
        self.assertEqual(self.ask({"op": "pause"})["state"], "pause_recorded_not_revocation")
        self.assertEqual(self.ask(req)["reason"], "paused_or_untrusted")
        db = self.store.connect()
        try:
            self.assertEqual(db.execute("SELECT state FROM admissions").fetchone()[0], "uncertain")
        finally:
            db.close()


    def test_authorized_partial_request_has_absolute_deadline(self):
        """A permitted peer trickling bytes cannot hold a worker indefinitely."""
        with mock.patch("wake_admission_broker.FRAME_TIMEOUT", 0.18):
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
                conn.settimeout(0.8)
                conn.connect(str(self.sock))
                conn.sendall(b"{")
                time.sleep(0.25)
                self.assertEqual(conn.recv(128), b"")
        self.assertEqual(self.ask({"op": "status"}), {"state": "ready", "outstanding": 0})

    def test_concurrent_partial_frames_cannot_exhaust_unbounded_threads(self):
        """Excess connection is refused; it never mutates the admission ledger."""
        self.stop()
        self.broker = Broker(self.sock, self.store, [os.getuid()], max_handlers=2)
        self.thread = threading.Thread(target=self.broker.serve_forever,
                                       kwargs={"poll_interval": .01}, daemon=True)
        self.thread.start()
        held = []
        try:
            for _ in range(2):
                conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                conn.connect(str(self.sock))
                conn.sendall(b"{")
                held.append(conn)
            time.sleep(0.08)
            with self.assertRaises((RuntimeError, OSError)):
                self.ask({"op": "status"})
        finally:
            for conn in held:
                conn.close()
        time.sleep(0.08)
        self.assertEqual(self.ask({"op": "status"})["outstanding"], 0)

    def test_slow_trickle_reply_has_absolute_deadline(self):
        """A peer answering a byte at a time cannot extend query forever."""
        reply_path = self.root / "slow-reply.sock"
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
            listener.bind(str(reply_path))
            listener.listen(1)
            def reply_slowly():
                with listener.accept()[0] as conn:
                    while conn.recv(4096):
                        pass
                    for _ in range(10):
                        try:
                            conn.sendall(b"{")
                        except OSError:
                            break
                        time.sleep(0.055)
            worker = threading.Thread(target=reply_slowly, daemon=True)
            worker.start()
            start = time.monotonic()
            with mock.patch("wake_admission_broker.FRAME_TIMEOUT", 0.18):
                with self.assertRaises((TimeoutError, OSError)):
                    query(reply_path, {"op": "status"})
            self.assertLess(time.monotonic() - start, 0.75)
            worker.join(timeout=1)


if __name__ == "__main__":
    unittest.main()
