"""Isolated B5 identity-scope policy tests; no ChatGPT/UI Send."""
import hashlib
import os
import socket
import unittest
from unittest.mock import patch
from remote_security.admission_sender_scope import (SenderScopePolicy,
    AuthenticatedAdmissionProxy, kernel_uid)


class RecordingB1Store:
    def __init__(self):
        self.calls = []

    def request(self, req):
        self.calls.append(dict(req))
        return {"state": "admitted_not_delivered"}


class SenderScopeTests(unittest.TestCase):
    def setUp(self):
        self.policy = SenderScopePolicy(broker_uid=21001, controller_uid=21002,
                        sender_uids={21003: "chat-A", 21004: "chat-B"},
                        allowed_targets={"chat-B", "chat-C"},
                        sender_routes={"chat-A":{"chat-B"}, "chat-B":{"chat-C"}})
        self.admit = dict(op="admit", conversation_id="chat-B", message_id="m1",
                          origin_turn_id="turn-A", sender_id="chat-A",
                          payload_sha256=hashlib.sha256(b"approved").hexdigest())

    def check(self, uid, req=None):
        return self.policy.decide(uid, self.admit if req is None else req)

    def test_scoped_a_to_b(self):
        d = self.check(21003)
        self.assertTrue(d.permitted)
        self.assertEqual(d.reason, "uid_scoped_claim_only")

    def test_scoped_b_to_c(self):
        req = dict(self.admit, conversation_id="chat-C", sender_id="chat-B", origin_turn_id="turn-B")
        self.assertTrue(self.check(21004, req).permitted)

    def test_forged_sender_from_authorized_uid_rejected(self):
        self.assertEqual(self.check(21004).reason, "sender_uid_mismatch")
        self.assertFalse(self.check(21004).permitted)

    def test_claimed_origin_turn_is_not_authenticated_by_uid(self):
        # A genuine process UID does not prove a ChatGPT assistant produced this turn.
        forged = dict(self.admit, origin_turn_id="invented-source-turn")
        decision = self.check(21003, forged)
        self.assertTrue(decision.permitted)
        self.assertEqual(decision.reason, "uid_scoped_claim_only")

    def test_unmapped_peer_rejected(self):
        self.assertFalse(self.check(21005).permitted)

    def test_broker_cannot_impersonate_sender(self):
        self.assertFalse(self.check(21001).permitted)

    def test_controller_cannot_admit(self):
        self.assertFalse(self.check(21002).permitted)

    def test_sender_cannot_begin_click(self):
        req = dict(self.admit, op="begin_click")
        self.assertFalse(self.check(21003, req).permitted)
        self.assertTrue(self.check(21002, req).permitted)

    def test_sender_cannot_pause_but_controller_can(self):
        self.assertFalse(self.check(21003, {"op":"pause"}).permitted)
        self.assertTrue(self.check(21002, {"op":"pause"}).permitted)

    def test_status_read_only_for_scoped_uids(self):
        for uid in (21002,21003,21004):
            self.assertTrue(self.check(uid,{"op":"status"}).permitted)
        self.assertFalse(self.check(21005,{"op":"status"}).permitted)

    def test_sender_specific_route_blocks_a_to_c(self):
        req = dict(self.admit, conversation_id="chat-C")
        self.assertEqual(self.check(21003,req).reason,"sender_target_route_denied")

    def test_invalid_route_configuration_fails_closed(self):
        with self.assertRaises(ValueError):
            SenderScopePolicy(broker_uid=21001,controller_uid=21002,
                sender_uids={21003:"chat-A"},allowed_targets={"chat-B"},
                sender_routes={"chat-A":{"chat-C"}})

    def test_target_allowlist(self):
        self.assertEqual(self.check(21003,dict(self.admit,conversation_id="chat-X")).reason,
                         "target_not_allowlisted")

    def test_extra_fields_rejected(self):
        self.assertFalse(self.check(21003,dict(self.admit, override=True)).permitted)
        self.assertFalse(self.check(21003,{"op":"status","sender_id":"chat-A"}).permitted)

    def test_malformed_fields_rejected(self):
        for bad in (None, 123, True, "", "not sha", "A"*65):
            self.assertFalse(self.check(21003,dict(self.admit,payload_sha256=bad)).permitted)
        self.assertFalse(self.check(21003,dict(self.admit,origin_turn_id="../foo")).permitted)

    def test_invalid_peer_uid_rejected(self):
        for uid in (True,-1,"21003",None):
            self.assertFalse(self.check(uid).permitted)

    def test_unknown_operation_rejected(self):
        self.assertFalse(self.check(21003,dict(self.admit,op="retire")).permitted)
        self.assertFalse(self.check(21003,dict(self.admit,op="send")).permitted)

    def test_role_collisions_rejected(self):
        for kwargs in (dict(broker_uid=21002,controller_uid=21002,sender_uids={21003:"chat-A"}),
                       dict(broker_uid=21001,controller_uid=21002,sender_uids={21002:"chat-A"}),
                       dict(broker_uid=21001,controller_uid=21002,sender_uids={21003:"chat-A",21004:"chat-A"}),
                       dict(broker_uid=True,controller_uid=21002,sender_uids={21003:"chat-A"})):
            with self.assertRaises(ValueError):
                SenderScopePolicy(allowed_targets={"chat-B"}, sender_routes={"chat-A":{"chat-B"}},**kwargs)

    def test_policy_mapping_is_immutable(self):
        with self.assertRaises(TypeError):
            self.policy.sender_uids[21003] = "chat-C"

    def test_unscoped_store_call_fails_closed(self):
        inner = RecordingB1Store()
        policy = SenderScopePolicy(broker_uid=os.geteuid(), controller_uid=21002,
                                   sender_uids={21003:"chat-A"}, allowed_targets={"chat-B"},
                                   sender_routes={"chat-A":{"chat-B"}})
        proxy = AuthenticatedAdmissionProxy(inner,policy)
        with self.assertRaises(PermissionError):
            proxy.request(self.admit)
        self.assertEqual(inner.calls,[])

    def test_kernel_uid_on_real_unix_socketpair(self):
        a,b = socket.socketpair(socket.AF_UNIX,socket.SOCK_STREAM)
        try:
            self.assertEqual(kernel_uid(a),os.getuid())
            self.assertEqual(kernel_uid(b),os.getuid())
        finally:
            a.close();b.close()

    def test_non_unix_socket_rejected(self):
        s=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
        try:
            with self.assertRaises(ValueError):
                kernel_uid(s)
        finally:
            s.close()

    def test_proxy_rejects_unauthorized_without_forwarding(self):
        inner=RecordingB1Store()
        policy=SenderScopePolicy(broker_uid=os.geteuid(),controller_uid=21002,
                                 sender_uids={21003:"chat-B"},allowed_targets={"chat-B"},
                                 sender_routes={"chat-B":{"chat-B"}})
        proxy=AuthenticatedAdmissionProxy(inner,policy)
        a,b=socket.socketpair(socket.AF_UNIX,socket.SOCK_STREAM)
        try:
            self.assertEqual(proxy.request_from_socket(a,self.admit)["reason"],"sender_uid_mismatch")
            self.assertEqual(inner.calls,[])
        finally:
            a.close();b.close()

    def test_proxy_rejects_wrong_broker_process_uid(self):
        inner=RecordingB1Store()
        with self.assertRaises(PermissionError):
            AuthenticatedAdmissionProxy(inner,self.policy)

    def test_broker_uid_change_after_proxy_creation_fails_closed(self):
        inner=RecordingB1Store()
        policy=SenderScopePolicy(broker_uid=os.geteuid(),controller_uid=21002,
                                 sender_uids={21003:"chat-A"},allowed_targets={"chat-B"},
                                 sender_routes={"chat-A":{"chat-B"}})
        proxy=AuthenticatedAdmissionProxy(inner,policy)
        a,b=socket.socketpair(socket.AF_UNIX,socket.SOCK_STREAM)
        try:
            with patch("remote_security.admission_sender_scope.os.geteuid",return_value=21001):
                self.assertEqual(proxy.request_from_socket(a,self.admit)["reason"],"broker_uid_changed")
            self.assertEqual(inner.calls,[])
        finally:
            a.close();b.close()

    def test_proxy_rejects_tcp_connection_without_forwarding(self):
        inner=RecordingB1Store()
        policy=SenderScopePolicy(broker_uid=os.geteuid(),controller_uid=21002,
                                 sender_uids={21003:"chat-A"},allowed_targets={"chat-B"},
                                 sender_routes={"chat-A":{"chat-B"}})
        proxy=AuthenticatedAdmissionProxy(inner,policy)
        with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as conn:
            self.assertEqual(proxy.request_from_socket(conn,self.admit)["reason"],"missing_kernel_peer")
        self.assertEqual(inner.calls,[])

    def test_proxy_rejects_invalid_connection(self):
        inner=RecordingB1Store()
        policy=SenderScopePolicy(broker_uid=os.geteuid(),controller_uid=21002,
                                 sender_uids={21003:"chat-A"},allowed_targets={"chat-B"},
                                 sender_routes={"chat-A":{"chat-B"}})
        proxy=AuthenticatedAdmissionProxy(inner,policy)
        self.assertEqual(proxy.request_from_socket(None,self.admit)["reason"],"missing_kernel_peer")
        self.assertEqual(inner.calls,[])


if __name__ == '__main__':
    unittest.main()
