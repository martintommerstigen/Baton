"""B5/R22 negative tests: source witness != ChatGPT authorship.

The default suite uses a disposable SQLite B1-compatible stub. An additional
CI step sets B1_H20_BROKER to the pinned original H20 broker file, exercising
its actual AF_UNIX handler and AdmissionStore (not a replacement model).
"""
from contextlib import closing, ExitStack
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import socket
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch

from remote_security.observed_source_handoff import ObservedSourceHandoff


class DisposableStore:
    """Minimal B1 state machine for isolated tests; NOT a deployment broker."""
    def __init__(self, path, pause, allowed):
        self.path = str(path)
        self.pause = Path(pause)
        self.allowed = frozenset(allowed)
        self.calls = []
        self.fail_admit = False
        with closing(self.connect()) as db:
            db.executescript("""CREATE TABLE admissions (
              conversation_id TEXT PRIMARY KEY, message_id TEXT UNIQUE,
              sender_id TEXT, origin_turn_id TEXT, payload_sha256 TEXT,
              state TEXT NOT NULL);
              CREATE TABLE settings (key TEXT PRIMARY KEY,value TEXT);""")

    def connect(self):
        return sqlite3.connect(self.path, timeout=5, isolation_level=None)

    def request(self, req):
        self.calls.append(dict(req))
        op = req["op"]
        if op == "status":
            return {"state": "paused" if self.pause.exists() else "ready"}
        if op == "pause":
            self.pause.touch()
            return {"state": "pause_recorded_not_revocation"}
        if self.pause.exists():
            return {"state": "rejected", "reason": "paused_or_untrusted"}
        if op == "admit" and self.fail_admit:
            raise OSError("injected failure after durable witness spend")
        with closing(self.connect()) as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                if op == "admit":
                    try:
                        db.execute("""INSERT INTO admissions VALUES
                            (?,?,?,?,?,'admitted')""",
                            (req["conversation_id"], req["message_id"],
                             req["sender_id"], req["origin_turn_id"],
                             req["payload_sha256"]))
                        result = {"state": "admitted_not_delivered"}
                    except sqlite3.IntegrityError:
                        result = {"state": "rejected", "reason": "outstanding_attempt"}
                elif op == "begin_click":
                    row = db.execute("""SELECT message_id,sender_id,origin_turn_id,
                        payload_sha256,state FROM admissions
                        WHERE conversation_id=?""",
                        (req["conversation_id"],)).fetchone()
                    expected = tuple(req[k] for k in ("message_id","sender_id",
                                    "origin_turn_id","payload_sha256")) + ("admitted",)
                    if row != expected:
                        result = {"state": "rejected", "reason": "attempt_closed"}
                    else:
                        db.execute("UPDATE admissions SET state='uncertain' WHERE conversation_id=?",
                                   (req["conversation_id"],))
                        result = {"state": "click_started_uncertain"}
                else:
                    result = {"state": "rejected", "reason": "unsupported"}
                db.execute("COMMIT")
                return result
            except BaseException:
                db.execute("ROLLBACK")
                raise


class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = DisposableStore(self.root/"b1.sqlite", self.root/"PAUSE_UI_WRITES",
                                     {"chat-B","chat-C"})
        self.broker_uid = os.geteuid()
        self.observer_uid = self.broker_uid + 10001
        self.controller_uid = self.broker_uid + 10002
        self.routes = {"chat-A":{"chat-B"}, "chat-B":{"chat-C"}}
        self.proxy = self.new_proxy()
        self.envelope = dict(conversation_id="chat-B",message_id="m1",
                             origin_turn_id="turn-A",sender_id="chat-A",
                             payload_sha256=hashlib.sha256(b"approved").hexdigest())
        self.observation = dict(self.envelope,op="observe_source",
                 source_text_sha256=hashlib.sha256(b"observed assistant text").hexdigest())

    def new_proxy(self):
        return ObservedSourceHandoff(self.store,broker_uid=self.broker_uid,
                   observer_uid=self.observer_uid,controller_uid=self.controller_uid,
                   source_routes=self.routes)

    def call(self, uid, req):
        with ExitStack() as stack:
            a,b = socket.socketpair(socket.AF_UNIX,socket.SOCK_STREAM)
            stack.enter_context(a); stack.enter_context(b)
            with patch("remote_security.observed_source_handoff.kernel_uid",return_value=uid):
                return self.proxy.request_from_socket(a,req)

    def admit(self, **changes):
        return self.call(self.controller_uid,dict(self.envelope,op="admit",**changes))

    def observe(self, **changes):
        return self.call(self.observer_uid,dict(self.observation,**changes))

    def test_observer_then_controller_admit_and_begin_click(self):
        self.assertEqual(self.observe()["state"],"source_observation_recorded_not_authorship")
        self.assertEqual(self.admit()["state"],"admitted_not_delivered")
        click = dict(self.envelope,op="begin_click")
        self.assertEqual(self.call(self.controller_uid,click)["state"],"click_started_uncertain")
        self.assertEqual(self.call(self.controller_uid,click)["state"],"rejected")

    def test_no_observation_cannot_admit(self):
        self.assertEqual(self.admit()["reason"],"no_source_observation")
        self.assertEqual(self.store.calls,[])

    def test_controller_cannot_self_observe(self):
        self.assertEqual(self.call(self.controller_uid,self.observation)["reason"],"observer_only")
        self.assertEqual(self.admit()["reason"],"no_source_observation")

    def test_observer_cannot_admit_or_click(self):
        self.observe()
        self.assertEqual(self.call(self.observer_uid,dict(self.envelope,op="admit"))["reason"],
                         "controller_only")
        self.assertEqual(self.call(self.observer_uid,dict(self.envelope,op="begin_click"))["reason"],
                         "controller_only")

    def test_witness_replay_and_same_turn_different_target(self):
        self.observe()
        self.assertEqual(self.observe()["reason"],"observation_replay")
        other = dict(self.observation,conversation_id="chat-C",message_id="m2")
        self.assertEqual(self.call(self.observer_uid,other)["reason"],
                         "invalid_observation_or_route")

    def test_same_source_turn_new_message_is_rejected(self):
        self.observe()
        self.assertEqual(self.observe(message_id="m2")["reason"],"observation_replay")

    def test_same_message_different_source_turn_is_rejected(self):
        self.observe()
        self.assertEqual(self.observe(origin_turn_id="turn-A2")["reason"],"observation_replay")

    def test_payload_mismatch_never_spends_witness(self):
        self.observe()
        self.assertEqual(self.admit(payload_sha256="b"*64)["reason"],
                         "observation_mismatch_or_spent")
        self.assertEqual(self.admit()["state"],"admitted_not_delivered")

    def test_wrong_message_mismatch(self):
        self.observe()
        self.assertEqual(self.admit(message_id="m2")["reason"],"observation_mismatch_or_spent")

    def test_cross_target_route_escalation(self):
        req = dict(self.observation,conversation_id="chat-C")
        self.assertEqual(self.call(self.observer_uid,req)["reason"],
                         "invalid_observation_or_route")
        self.assertEqual(self.admit(conversation_id="chat-C")["reason"],
                         "invalid_envelope_or_route")

    def test_b_to_c_explicit_route(self):
        observation = dict(self.observation,sender_id="chat-B",conversation_id="chat-C",
                           origin_turn_id="turn-B",message_id="m2")
        self.assertEqual(self.call(self.observer_uid,observation)["state"],
                         "source_observation_recorded_not_authorship")
        req = dict(observation)
        req.pop("source_text_sha256")
        req["op"]="admit"
        self.assertEqual(self.call(self.controller_uid,req)["state"],"admitted_not_delivered")

    def test_restart_keeps_spent_state(self):
        self.observe()
        self.admit()
        self.proxy = self.new_proxy()
        self.assertEqual(self.admit()["reason"],"observation_mismatch_or_spent")
        self.assertEqual(self.observe()["reason"],"observation_replay")

    def test_crash_after_spend_fails_closed(self):
        self.observe()
        self.store.fail_admit = True
        with self.assertRaises(OSError):
            self.admit()
        self.store.fail_admit = False
        self.proxy = self.new_proxy()
        self.assertEqual(self.admit()["reason"],"observation_mismatch_or_spent")
        self.assertEqual(self.store.calls[-1]["op"],"admit")

    def test_pause_blocks_inner_admission_and_consumes_witness(self):
        self.observe()
        self.store.pause.touch()
        self.assertEqual(self.admit()["reason"],"paused_or_untrusted")
        self.store.pause.unlink()
        self.assertEqual(self.admit()["reason"],"observation_mismatch_or_spent")

    def test_concurrent_admits_exactly_one_spend(self):
        self.observe()
        barrier = threading.Barrier(2)
        outcomes = []
        lock = threading.Lock()
        def work():
            barrier.wait()
            result = self.admit()
            with lock:
                outcomes.append(result["state"])
        threads = [threading.Thread(target=work) for _ in range(2)]
        for t in threads: t.start()
        for t in threads: t.join(timeout=8)
        self.assertFalse(any(t.is_alive() for t in threads))
        self.assertEqual(outcomes.count("admitted_not_delivered"),1)
        self.assertEqual(outcomes.count("rejected"),1)

    def test_source_text_digest_is_not_source_authentication(self):
        forged = "a"*64
        self.assertEqual(self.observe(source_text_sha256=forged)["state"],
                         "source_observation_recorded_not_authorship")
        # A real authorized observer UID can lie. This is an explicit NEG.
        self.assertEqual(self.admit()["state"],"admitted_not_delivered")

    def test_malformed_and_extra_fields(self):
        self.assertEqual(self.observe(source_text_sha256="bad")["reason"],
                         "invalid_observation_or_route")
        self.assertEqual(self.observe(payload_sha256="X"*64)["reason"],
                         "invalid_observation_or_route")
        self.assertEqual(self.observe(origin_turn_id="../bad")["reason"],
                         "invalid_observation_or_route")
        self.assertEqual(self.observe(extra=True)["reason"],
                         "invalid_observation_or_route")
        self.assertEqual(self.admit(extra=True)["reason"],"invalid_envelope_or_route")

    def test_missing_kernel_peer_and_tcp(self):
        with patch("remote_security.observed_source_handoff.kernel_uid",side_effect=ValueError):
            self.assertEqual(self.proxy.request_from_socket(None,self.observation)["reason"],
                             "missing_kernel_peer")
        with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as conn:
            self.assertEqual(self.proxy.request_from_socket(conn,self.observation)["reason"],
                             "missing_kernel_peer")

    def test_role_collision_and_bad_route_fail_closed(self):
        with self.assertRaises(ValueError):
            ObservedSourceHandoff(self.store,broker_uid=self.broker_uid,
                observer_uid=self.observer_uid,controller_uid=self.observer_uid,
                source_routes=self.routes)
        with self.assertRaises(ValueError):
            ObservedSourceHandoff(self.store,broker_uid=self.broker_uid,
                observer_uid=self.observer_uid,controller_uid=self.controller_uid,
                source_routes={"chat-A":{"chat-X"}})

    def test_broker_uid_rechecked(self):
        with patch("remote_security.observed_source_handoff.os.geteuid",
                   return_value=self.broker_uid+9):
            self.assertEqual(self.proxy.request_from_socket(None,self.observation)["reason"],
                             "broker_uid_changed")

    def test_status_and_pause_roles(self):
        self.assertEqual(self.call(self.observer_uid,{"op":"status"})["state"],"ready")
        self.assertEqual(self.call(self.observer_uid,{"op":"pause"})["reason"],"controller_only")
        self.assertEqual(self.call(self.controller_uid,{"op":"pause"})["state"],
                         "pause_recorded_not_revocation")
        self.assertEqual(self.call(self.controller_uid,{"op":"status"})["state"],"paused")

    def test_unscoped_api_and_unknown_op(self):
        with self.assertRaises(PermissionError):
            self.proxy.request(dict(self.envelope,op="admit"))
        self.assertEqual(self.call(self.controller_uid,{"op":"send"})["reason"],
                         "unsupported_operation")
        self.assertEqual(self.call(self.controller_uid,{"op":"retire"})["reason"],
                         "unsupported_operation")

    def test_begin_click_without_admission_rejected(self):
        self.assertEqual(self.call(self.controller_uid,dict(self.envelope,op="begin_click"))["state"],
                         "rejected")

    def test_wrong_broker_uid_constructor_rejected(self):
        with self.assertRaises(PermissionError):
            ObservedSourceHandoff(self.store,broker_uid=self.broker_uid+4,
                observer_uid=self.observer_uid,controller_uid=self.controller_uid,
                source_routes=self.routes)


class PinnedB1H20Contract(unittest.TestCase):
    """Optional *actual* H20 AF_UNIX+SQLite contract, not a UI integration."""
    @unittest.skipUnless(os.environ.get("B1_H20_BROKER"),"pinned B1 H20 checkout absent")
    def test_real_h20_handler_store_pause_restart_and_replay(self):
        path = Path(os.environ["B1_H20_BROKER"]).resolve(strict=True)
        spec = importlib.util.spec_from_file_location("pinned_b1_h20_broker",path)
        b1 = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(b1)
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            os.chmod(root,0o700)
            db=root/"actual_b1.sqlite"
            pause=root/"PAUSE_UI_WRITES"
            sock=root/"admission.sock"
            broker_uid=os.geteuid()
            observer_uid=broker_uid+10001
            controller_uid=broker_uid+10002
            inner=b1.AdmissionStore(db,pause,{"chat-B"})
            proxy=ObservedSourceHandoff(inner,broker_uid=broker_uid,
                     observer_uid=observer_uid,controller_uid=controller_uid,
                     source_routes={"chat-A":{"chat-B"}})
            broker=b1.Broker(sock,proxy,[os.getuid()])
            thread=threading.Thread(target=broker.serve_forever,
                         kwargs={"poll_interval":0.01},daemon=True)
            thread.start()
            envelope=dict(conversation_id="chat-B",message_id="m1",
                origin_turn_id="turn-A",sender_id="chat-A",
                payload_sha256=hashlib.sha256(b"approved").hexdigest())
            def ask(uid,req):
                with patch("remote_security.observed_source_handoff.kernel_uid",
                           return_value=uid):
                    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as client:
                        client.settimeout(4)
                        client.connect(str(sock))
                        client.sendall((json.dumps(req)+"\n").encode())
                        reply=bytearray()
                        while not reply.endswith(b"\n"):
                            part=client.recv(4096)
                            if not part: break
                            reply.extend(part)
                        return json.loads(reply)
            try:
                self.assertEqual(ask(controller_uid,dict(envelope,op="admit"))["reason"],
                                 "no_source_observation")
                observed=dict(envelope,op="observe_source",
                     source_text_sha256="c"*64)
                self.assertEqual(ask(observer_uid,observed)["state"],
                                 "source_observation_recorded_not_authorship")
                self.assertEqual(ask(controller_uid,dict(envelope,op="admit"))["state"],
                                 "admitted_not_delivered")
                self.assertEqual(ask(controller_uid,dict(envelope,op="begin_click"))["state"],
                                 "click_started_uncertain")
                self.assertEqual(ask(controller_uid,dict(envelope,op="begin_click"))["state"],
                                 "rejected")
                self.assertEqual(ask(controller_uid,dict(envelope,op="admit"))["state"],
                                 "rejected")
                self.assertEqual(ask(controller_uid,{"op":"pause"})["state"],
                                 "pause_recorded_not_revocation")
                self.assertEqual(ask(controller_uid,{"op":"status"})["state"],"paused")
            finally:
                broker.shutdown()
                broker.server_close()
                thread.join(timeout=5)
            # Fresh proxy + actual B1 SQLite still cannot re-admit.
            restarted=b1.AdmissionStore(db,pause,{"chat-B"})
            new_proxy=ObservedSourceHandoff(restarted,broker_uid=broker_uid,
                 observer_uid=observer_uid,controller_uid=controller_uid,
                 source_routes={"chat-A":{"chat-B"}})
            with ExitStack() as stack:
                a,b = socket.socketpair()
                stack.enter_context(a); stack.enter_context(b)
                with patch("remote_security.observed_source_handoff.kernel_uid",
                           return_value=controller_uid):
                    self.assertEqual(new_proxy.request_from_socket(a,dict(envelope,op="admit"))["state"],
                                     "rejected")


if __name__ == "__main__":
    unittest.main()
