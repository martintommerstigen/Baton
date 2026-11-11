"""B5-RJ16: no live UI, only Linux AF_UNIX kernel and negative controls."""
import os
import socket
import struct
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from remote_security.frame_credentials import (
    UntrustedFrame, IncompleteFrame, enable_listener_credentials,
    read_authenticated_frame,
)


@unittest.skipUnless(os.name == 'posix' and hasattr(socket, 'SO_PASSCRED')
                     and hasattr(socket, 'SCM_CREDENTIALS'), 'Linux only')
class FrameTests(unittest.TestCase):
    def pair(self):
        a, b = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
        a.setsockopt(socket.SOL_SOCKET, socket.SO_PASSCRED, 1)
        return a, b

    def test_valid_frame_and_uid(self):
        if os.getuid() == 0:
            self.skipTest('root is never an authorized production connector')
        a,b = self.pair()
        with a,b:
            b.sendall(b'{"op":"status"}\n')
            frame,uid = read_authenticated_frame(a,allowed_uids={os.getuid()})
            self.assertEqual(frame,b'{"op":"status"}\n')
            self.assertEqual(uid,os.getuid())

    def test_root_connector_denied(self):
        if os.getuid()!=0:self.skipTest('root-only negative')
        a,b=self.pair()
        with a,b:
            b.sendall(b'ok\n')
            with self.assertRaises(UntrustedFrame):
                read_authenticated_frame(a,allowed_uids={21003})

    def test_invalid_schema_and_bounds(self):
        a,b=self.pair()
        with a,b:
            for kw in ({'allowed_uids':set()}, {'allowed_uids':{0}},
                       {'allowed_uids':{True}}, {'allowed_uids':{21003},'limit':8193},
                       {'allowed_uids':{21003},'timeout':0}):
                with self.subTest(kw=kw),self.assertRaises(ValueError):
                    read_authenticated_frame(a,**kw)

    def test_tcp_denied(self):
        with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as tcp:
            with self.assertRaises(UntrustedFrame):
                read_authenticated_frame(tcp,allowed_uids={21003})

    def test_listener_must_enable_passcred(self):
        a,b=socket.socketpair()
        with a,b:
            with self.assertRaises(UntrustedFrame):
                read_authenticated_frame(a,allowed_uids={21003})

    def test_multi_frame_rejected(self):
        if os.getuid()==0:self.skipTest('cross-UID suite tests real frame')
        a,b=self.pair()
        with a,b:
            b.sendall(b'a\nb\n')
            with self.assertRaises(UntrustedFrame):
                read_authenticated_frame(a,allowed_uids={os.getuid()})

    def test_incomplete_frame_denied(self):
        if os.getuid()==0:self.skipTest('cross-UID suite tests real frame')
        a,b=self.pair()
        with a,b:
            b.sendall(b'incomplete')
            b.shutdown(socket.SHUT_WR)
            with self.assertRaises(IncompleteFrame):
                read_authenticated_frame(a,allowed_uids={os.getuid()})

    def test_absolute_deadline(self):
        if os.getuid()==0:self.skipTest('cross-UID suite tests real frame')
        a,b=self.pair()
        with a,b:
            b.sendall(b'x')
            with self.assertRaises(IncompleteFrame):
                read_authenticated_frame(a,allowed_uids={os.getuid()},timeout=.03)

    def test_enable_listener(self):
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as l:
            enable_listener_credentials(l)
            self.assertEqual(l.getsockopt(socket.SOL_SOCKET,socket.SO_PASSCRED),1)
        with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as l:
            with self.assertRaises(UntrustedFrame):enable_listener_credentials(l)


@unittest.skipUnless(os.geteuid()==0 and hasattr(os,'fork') and hasattr(socket,'SO_PASSCRED'),
                     'isolated privileged Linux runner only')
class CrossUID(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        os.chmod(self.tmp.name,0o711)
        self.path=str(Path(self.tmp.name)/'broker.sock')
        self.listener=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
        enable_listener_credentials(self.listener)
        self.listener.bind(self.path)
        os.chmod(self.path,0o777) # permissive on purpose; kernel identity is the test
        self.listener.listen(4)
        self.listener.settimeout(3)

    def tearDown(self):
        self.listener.close()
        self.tmp.cleanup()

    def child(self,uid,func):
        pid=os.fork()
        if pid==0:
            try:
                os.setgroups([])
                os.setgid(uid)
                os.setuid(uid)
                func()
                os._exit(0)
            except BaseException:
                os._exit(1)
        return pid

    def wait(self,pid):
        _,status=os.waitpid(pid,0)
        self.assertTrue(os.WIFEXITED(status) and os.WEXITSTATUS(status)==0)

    def test_valid_real_uid_and_early_send(self):
        def sender():
            with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as c:
                c.connect(self.path)
                c.sendall(b'one\n') # can send before accept: listener already has PASSCRED
        pid=self.child(21003,sender)
        with self.listener.accept()[0] as s:
            self.assertEqual(read_authenticated_frame(s,allowed_uids={21003}),
                             (b'one\n',21003))
        self.wait(pid)

    def test_wrong_connector_uid(self):
        def sender():
            with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as c:
                c.connect(self.path)
                c.sendall(b'forged\n')
        pid=self.child(21004,sender)
        with self.listener.accept()[0] as s:
            with self.assertRaises(UntrustedFrame):
                read_authenticated_frame(s,allowed_uids={21003})
        self.wait(pid)

    def test_delegated_fd_other_uid_rejected(self):
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as c:
            os.seteuid(21003)
            try:c.connect(self.path)
            finally:os.seteuid(0)
            def sender():c.sendall(b'delegated\n')
            pid=self.child(21004,sender)
            with self.listener.accept()[0] as s:
                # SO_PEERCRED alone sees 21003; SCM_CREDENTIALS sees 21004.
                raw=s.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12)
                self.assertEqual(struct.unpack('3i',raw)[1],21003)
                with self.assertRaises(UntrustedFrame):
                    read_authenticated_frame(s,allowed_uids={21003})
            self.wait(pid)

    def test_delegated_fd_same_uid_other_pid_rejected(self):
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as c:
            os.seteuid(21003)
            try:c.connect(self.path)
            finally:os.seteuid(0)
            pid=self.child(21003,lambda:c.sendall(b'fork\n'))
            with self.listener.accept()[0] as s:
                with self.assertRaises(UntrustedFrame):
                    read_authenticated_frame(s,allowed_uids={21003})
            self.wait(pid)

    def test_mixed_writers_rejected(self):
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as c:
            os.seteuid(21003)
            try:c.connect(self.path);c.sendall(b'part')
            finally:os.seteuid(0)
            pid=self.child(21004,lambda:c.sendall(b'two\n'))
            with self.listener.accept()[0] as s:
                with self.assertRaises(UntrustedFrame):
                    read_authenticated_frame(s,allowed_uids={21003})
            self.wait(pid)

    def test_oversized_frame_denied(self):
        def sender():
            with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as c:
                c.connect(self.path)
                c.sendall(b'x'*128+b'\n')
        pid=self.child(21003,sender)
        with self.listener.accept()[0] as s:
            with self.assertRaises(UntrustedFrame):
                read_authenticated_frame(s,allowed_uids={21003},limit=64)
        self.wait(pid)

    def test_multiple_frames_denied(self):
        def sender():
            with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as c:
                c.connect(self.path)
                c.sendall(b'one\ntwo\n')
        pid=self.child(21003,sender)
        with self.listener.accept()[0] as s:
            with self.assertRaises(UntrustedFrame):
                read_authenticated_frame(s,allowed_uids={21003})
        self.wait(pid)


if __name__=='__main__':unittest.main()
