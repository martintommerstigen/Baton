"""Trusted-push-only kernel UID tests; no UI or production credentials."""
import hashlib
import os
from pathlib import Path
import socket
import tempfile
import unittest
from remote_security.admission_sender_scope import (AuthenticatedAdmissionProxy,
    SenderScopePolicy, kernel_uid)


class StubStore:
    def __init__(self):
        self.calls=[]
    def request(self,req):
        self.calls.append(req.copy())
        return {"state":"admitted_not_delivered"}


@unittest.skipUnless(os.name == "posix" and hasattr(os, "seteuid") and
                     os.geteuid() == 0 and hasattr(socket, "SO_PEERCRED"),
                     "requires isolated privileged Linux runner")
class RealUIDBinding(unittest.TestCase):
    def test_distinct_uids_and_forged_sender(self):
        for client_uid, sender_id, expected_state, expected_calls in (
            (21003,"chat-A","admitted_not_delivered",1),
            (21004,"chat-A","rejected",0),
            (21003,"chat-B","rejected",0),
        ):
            with self.subTest(client_uid=client_uid,sender_id=sender_id):
                with tempfile.TemporaryDirectory() as root:
                    os.chmod(root,0o711)
                    path=str(Path(root)/"scope.sock")
                    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as listener:
                        listener.bind(path)
                        os.chmod(path,0o777) # intentionally permissive: kernel UID is authority
                        listener.listen(1)
                        listener.settimeout(3)
                        pid=os.fork()
                        if pid == 0:
                            try:
                                os.setgroups([])
                                os.setgid(client_uid)
                                os.setuid(client_uid)
                                with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as c:
                                    c.settimeout(3)
                                    c.connect(path)
                                    c.sendall(b"x")
                                os._exit(0)
                            except BaseException:
                                os._exit(1)
                        try:
                            os.seteuid(21001)
                            with listener.accept()[0] as conn:
                                conn.settimeout(3)
                                self.assertEqual(conn.recv(1),b"x")
                                self.assertEqual(kernel_uid(conn),client_uid)
                                policy=SenderScopePolicy(broker_uid=21001,
                                    controller_uid=21002,sender_uids={21003:"chat-A",21004:"chat-B"},
                                    allowed_targets={"chat-B"},
                                    sender_routes={"chat-A":{"chat-B"},"chat-B":{"chat-B"}})
                                store=StubStore()
                                proxy=AuthenticatedAdmissionProxy(store,policy)
                                req=dict(op="admit",conversation_id="chat-B",message_id="m1",
                                    origin_turn_id="turn-A",sender_id=sender_id,
                                    payload_sha256=hashlib.sha256(b"approved").hexdigest())
                                response=proxy.request_from_socket(conn,req)
                                self.assertEqual(response["state"],expected_state)
                                self.assertEqual(len(store.calls),expected_calls)
                        finally:
                            os.seteuid(0)
                            _,status=os.waitpid(pid,0)
                            self.assertTrue(os.WIFEXITED(status) and os.WEXITSTATUS(status)==0)


    def test_delegated_fd_keeps_connect_time_credentials(self):
        # Negative boundary: SO_PEERCRED is NOT per-message writer identity.
        with tempfile.TemporaryDirectory() as root:
            os.chmod(root,0o711)
            path=str(Path(root)/"delegated.sock")
            with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as listener:
                listener.bind(path)
                os.chmod(path,0o777)
                listener.listen(1)
                listener.settimeout(3)
                with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as client:
                    os.seteuid(21003)
                    try:
                        client.connect(path)
                    finally:
                        os.seteuid(0)
                    pid=os.fork()
                    if pid == 0:
                        try:
                            os.setgroups([])
                            os.setgid(21004)
                            os.setuid(21004)
                            client.sendall(b"delegated-writer")
                            os._exit(0)
                        except BaseException:
                            os._exit(1)
                    try:
                        with listener.accept()[0] as conn:
                            conn.settimeout(3)
                            self.assertEqual(conn.recv(16),b"delegated-writer")
                            # Credential is still the original CONNECTOR UID,
                            # even though a distinct UID wrote the bytes.
                            self.assertEqual(kernel_uid(conn),21003)
                    finally:
                        _,status=os.waitpid(pid,0)
                        self.assertTrue(os.WIFEXITED(status) and os.WEXITSTATUS(status)==0)


if __name__=="__main__":
    unittest.main()
