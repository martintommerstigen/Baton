"""B1/B5 offline admission tests. No UI, Greg or production files touched."""
import hashlib
import json
import os
from pathlib import Path
import socket
import socketserver
import stat
import tempfile
import threading
import time
import unittest
from unittest import mock

from wake_admission_broker import AdmissionStore, Broker, query, pause_present_or_untrusted, main


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
        second = self.envelope("chat-C", "m2")
        second.update(sender_id="chat-B", origin_turn_id="turn-B")
        self.assertEqual(self.ask(second)["state"], "admitted_not_delivered")

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

    def test_cross_target_message_id_replay_rejected(self):
        self.assertEqual(self.ask(self.envelope())["state"], "admitted_not_delivered")
        other = self.envelope("chat-C", "m1")
        other.update(sender_id="chat-B", origin_turn_id="turn-B")
        self.assertEqual(self.ask(other),
                         {"state": "rejected", "reason": "outstanding_attempt"})
        self.assertEqual(self.ask({"op": "status"})["outstanding"], 1)

    def test_cross_target_asserted_source_turn_double_spend_rejected(self):
        self.assertEqual(self.ask(self.envelope())["state"], "admitted_not_delivered")
        self.assertEqual(self.ask(self.envelope("chat-C", "m2")),
                         {"state": "rejected", "reason": "outstanding_attempt"})
        self.assertEqual(self.ask({"op": "status"})["outstanding"], 1)

    def test_source_turn_scope_is_sender_specific(self):
        self.assertEqual(self.ask(self.envelope())["state"], "admitted_not_delivered")
        other = self.envelope("chat-C", "m2")
        other["sender_id"] = "chat-B"
        self.assertEqual(self.ask(other)["state"], "admitted_not_delivered")

    def test_cross_target_replay_remains_blocked_after_restart(self):
        self.assertEqual(self.ask(self.envelope())["state"], "admitted_not_delivered")
        self.stop()
        self.store = AdmissionStore(self.db, self.pause, self.allowed)
        self.broker = Broker(self.sock, self.store, [os.getuid()])
        self.thread = threading.Thread(target=self.broker.serve_forever,
                                       kwargs={"poll_interval": .01}, daemon=True)
        self.thread.start()
        self.assertEqual(self.ask(self.envelope("chat-C", "m2"))["reason"],
                         "outstanding_attempt")
        self.assertEqual(self.ask({"op": "status"})["outstanding"], 1)

    def test_concurrent_cross_target_source_double_spend(self):
        barrier = threading.Barrier(2)
        outcomes = []
        lock = threading.Lock()
        def send(req):
            barrier.wait()
            response = self.ask(req)
            with lock:
                outcomes.append(response["state"])
        threads = [threading.Thread(target=send, args=(self.envelope(target, msg),))
                   for target, msg in (("chat-B", "m1"), ("chat-C", "m2"))]
        for t in threads: t.start()
        for t in threads: t.join(timeout=5)
        self.assertFalse(any(t.is_alive() for t in threads))
        self.assertEqual(outcomes.count("admitted_not_delivered"), 1)
        self.assertEqual(outcomes.count("rejected"), 1)
        self.assertEqual(self.ask({"op": "status"})["outstanding"], 1)

    def test_legacy_duplicate_source_rows_fail_closed_during_migration(self):
        import sqlite3
        self.stop()
        legacy = self.root / "legacy.sqlite"
        with sqlite3.connect(legacy) as db:
            db.executescript("""CREATE TABLE admissions (
                conversation_id TEXT PRIMARY KEY, message_id TEXT NOT NULL,
                origin_turn_id TEXT NOT NULL, sender_id TEXT NOT NULL,
                payload_sha256 TEXT NOT NULL, state TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
                CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);""")
            for target, msg in (("chat-B", "m1"), ("chat-C", "m2")):
                db.execute("""INSERT INTO admissions
                    (conversation_id,message_id,origin_turn_id,sender_id,payload_sha256,state)
                    VALUES (?,?,?,?,?,'admitted')""",
                    (target, msg, "turn-A", "chat-A", "a" * 64))
        with self.assertRaises(sqlite3.IntegrityError):
            AdmissionStore(legacy, self.pause, self.allowed)
        with sqlite3.connect(legacy) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM admissions").fetchone()[0], 2)

    def test_default_private_socket_mode_is_0600(self):
        self.assertEqual(stat.S_IMODE(self.sock.stat().st_mode), 0o600)
        self.assertTrue(self.broker.endpoint_unchanged())

    def test_opt_in_group_socket_0660_and_identity_check(self):
        self.stop()
        parent = self.root / "shared"
        parent.mkdir(mode=0o710)
        parent.chmod(0o710)
        path = parent / "broker.sock"
        broker = Broker(path, self.store, [os.getuid()], shared_gid=os.getegid())
        try:
            st = path.stat()
            self.assertEqual(stat.S_IMODE(st.st_mode), 0o660)
            self.assertEqual(st.st_gid, os.getegid())
            self.assertTrue(broker.endpoint_unchanged())
            worker = threading.Thread(target=broker.serve_forever,
                                      kwargs={"poll_interval": .01}, daemon=True)
            worker.start()
            self.assertEqual(query(path, {"op": "status"})["state"], "ready")
            broker.shutdown()
            worker.join(timeout=2)
        finally:
            broker.server_close()
        self.assertFalse(path.exists())

    def test_group_socket_rejects_nontraversable_parent(self):
        self.stop()
        parent = self.root / "no-traverse"
        parent.mkdir(mode=0o700)
        with self.assertRaises(PermissionError):
            Broker(parent / "broker.sock", self.store, [os.getuid()],
                   shared_gid=os.getegid())
        self.assertFalse((parent / "broker.sock").exists())

    def test_group_socket_rejects_group_writable_parent(self):
        self.stop()
        parent = self.root / "writable"
        parent.mkdir(mode=0o700)
        parent.chmod(0o770)
        with self.assertRaises(ValueError):
            Broker(parent / "broker.sock", self.store, [os.getuid()],
                   shared_gid=os.getegid())
        self.assertFalse((parent / "broker.sock").exists())

    def test_group_socket_rejects_invalid_group(self):
        self.stop()
        parent = self.root / "shared"
        parent.mkdir(mode=0o710)
        parent.chmod(0o710)
        for gid in (0, os.getegid() + 100000):
            with self.subTest(gid=gid), self.assertRaises((ValueError, PermissionError)):
                Broker(parent / "broker.sock", self.store, [os.getuid()],
                       shared_gid=gid)
        self.assertFalse((parent / "broker.sock").exists())

    def test_group_socket_mode_tamper_invalidates_endpoint(self):
        self.stop()
        parent = self.root / "shared"
        parent.mkdir(mode=0o710)
        parent.chmod(0o710)
        path = parent / "broker.sock"
        broker = Broker(path, self.store, [os.getuid()], shared_gid=os.getegid())
        try:
            self.assertTrue(broker.endpoint_unchanged())
            path.chmod(0o600)
            self.assertFalse(broker.endpoint_unchanged())
        finally:
            broker.server_close()

    def test_cli_distinct_uid_without_group_fails_before_db_or_bind(self):
        import sys
        from unittest import mock
        self.stop()
        db = self.root / "uncreated.sqlite"
        sock = self.root / "uncreated.sock"
        argv = ["wake_admission_broker.py", "--socket", str(sock),
                "--db", str(db), "--pause-path", str(self.pause),
                "--conversation", "chat-B", "--allow-uid", str(os.getuid() + 100000)]
        with mock.patch.object(sys, "argv", argv):
            with self.assertRaisesRegex(SystemExit, "requires --shared-gid"):
                main()
        self.assertFalse(db.exists())
        self.assertFalse(sock.exists())

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
            # Early fail-closed close with unread oversized bytes can produce RST.
            try:
                self.assertEqual(s.recv(128), b"")
            except ConnectionResetError:
                pass
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


    def test_socket_parent_symlink_rejected_before_bind(self):
        self.stop()
        actual = self.root / "actual"
        actual.mkdir(mode=0o700)
        link = self.root / "link"
        link.symlink_to(actual, target_is_directory=True)
        with self.assertRaises(ValueError):
            Broker(link / "broker.sock", self.store, [os.getuid()])
        self.assertFalse((actual / "broker.sock").exists())

    def test_socket_parent_swap_during_bind_fails_without_decoy_socket(self):
        """Inject a rename at the real AF_UNIX bind boundary."""
        self.stop()
        parent = self.root / "public"
        moved = self.root / "moved"
        decoy = self.root / "decoy"
        parent.mkdir(mode=0o700)
        decoy.mkdir(mode=0o700)
        original_bind = socketserver.UnixStreamServer.server_bind

        def swap_then_bind(server):
            parent.rename(moved)
            parent.symlink_to(decoy, target_is_directory=True)
            return original_bind(server)

        with mock.patch.object(socketserver.UnixStreamServer, "server_bind", swap_then_bind):
            with self.assertRaises(ValueError):
                Broker(parent / "broker.sock", self.store, [os.getuid()])
        self.assertFalse((decoy / "broker.sock").exists())
        self.assertFalse((moved / "broker.sock").exists())
        self.assertEqual(self.store.request({"op": "status"})["outstanding"], 0)

    def test_shutdown_unlinks_only_pinned_original_socket(self):
        """A replacement public path cannot make broker delete a decoy."""
        self.stop()
        parent = self.root / "public"
        moved = self.root / "moved"
        decoy = self.root / "decoy"
        parent.mkdir(mode=0o700)
        decoy.mkdir(mode=0o700)
        broker = Broker(parent / "broker.sock", self.store, [os.getuid()])
        parent.rename(moved)
        parent.symlink_to(decoy, target_is_directory=True)
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as other:
            other.bind(str(decoy / "broker.sock"))
            broker.server_close()
            self.assertTrue((decoy / "broker.sock").exists())
            self.assertFalse((moved / "broker.sock").exists())
        self.assertEqual(self.store.request({"op": "status"})["outstanding"], 0)




    def test_rebound_basename_before_dispatch_rejects_admission(self):
        """Accepted connection is not authority after unlink/rebind."""
        rogue = []
        def swap_after_read(_conn):
            self.sock.unlink()
            other = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            other.bind(str(self.sock))
            rogue.append(other)
            return (json.dumps(self.envelope()) + "\n").encode("utf-8")
        try:
            with mock.patch("wake_admission_broker.read_bounded_frame",
                            side_effect=swap_after_read):
                with self.assertRaises((RuntimeError, OSError)):
                    self.ask(self.envelope())
            self.assertFalse(self.broker.endpoint_unchanged())
            self.assertEqual(self.store.request({"op": "status"})["outstanding"], 0)
            self.assertTrue(self.sock.exists())
        finally:
            for other in rogue:
                other.close()

    def test_rebound_basename_after_admit_cannot_return_success(self):
        """Committed admission survives an uncertain reply and restart."""
        real_request = self.store.request
        rogue = []
        def swap_after_commit(req):
            result = real_request(req)
            if req.get("op") == "admit":
                self.sock.unlink()
                other = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                other.bind(str(self.sock))
                rogue.append(other)
            return result
        try:
            with mock.patch.object(self.store, "request", side_effect=swap_after_commit):
                with self.assertRaises((RuntimeError, OSError)):
                    self.ask(self.envelope())
            self.assertFalse(self.broker.endpoint_unchanged())
            self.assertEqual(real_request({"op": "status"})["outstanding"], 1)
            self.assertEqual(real_request(self.envelope())["reason"], "outstanding_attempt")
        finally:
            for other in rogue:
                other.close()
        self.stop()
        self.broker = Broker(self.sock, self.store, [os.getuid()])
        self.thread = threading.Thread(target=self.broker.serve_forever,
                                       kwargs={"poll_interval": .01}, daemon=True)
        self.thread.start()
        self.assertEqual(self.ask(self.envelope())["reason"], "outstanding_attempt")

    def test_rebound_basename_after_begin_click_keeps_uncertain(self):
        """A lost click-start receipt must never authorize a second click."""
        req = self.envelope()
        self.assertEqual(self.ask(req)["state"], "admitted_not_delivered")
        real_request = self.store.request
        rogue = []
        def swap_after_click(envelope):
            result = real_request(envelope)
            if envelope.get("op") == "begin_click":
                self.sock.unlink()
                other = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                other.bind(str(self.sock))
                rogue.append(other)
            return result
        try:
            with mock.patch.object(self.store, "request", side_effect=swap_after_click):
                with self.assertRaises((RuntimeError, OSError)):
                    self.ask(dict(req, op="begin_click"))
            self.assertFalse(self.broker.endpoint_unchanged())
            with self.store.connect() as db:
                self.assertEqual(db.execute("SELECT state FROM admissions").fetchone()[0],
                                 "uncertain")
        finally:
            for other in rogue:
                other.close()
        self.stop()
        self.broker = Broker(self.sock, self.store, [os.getuid()])
        self.thread = threading.Thread(target=self.broker.serve_forever,
                                       kwargs={"poll_interval": .01}, daemon=True)
        self.thread.start()
        self.assertEqual(self.ask(dict(req, op="begin_click"))["reason"],
                         "envelope_mismatch_or_attempt_closed")

if __name__ == "__main__":
    unittest.main()
