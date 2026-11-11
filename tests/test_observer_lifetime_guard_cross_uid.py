"""Actual Linux two-UID AF_UNIX query under R25 seccomp; synthetic source bytes."""
import json
import os
import signal
import socket
import sys
import tempfile
import unittest
from pathlib import Path

from remote_security.observer_lifetime_guard import install_observer_lifetime_guard
from remote_security.broker_peer import query_verified_broker


@unittest.skipUnless(sys.platform.startswith('linux') and os.geteuid() == 0,
                     'isolated root CI for actual UID transition only')
class CrossUidTests(unittest.TestCase):
    def test_seccomp_observer_can_query_real_distinct_uid_broker(self):
        broker_uid, observer_uid, shared_gid = 29111, 29112, 29113
        with tempfile.TemporaryDirectory(prefix='b5-r25-', dir='/tmp') as base:
            os.chmod(base, 0o755)
            directory = str(Path(base) / 'broker')
            os.mkdir(directory, 0o755)
            os.chown(directory, broker_uid, shared_gid)
            path = directory + '/snapshot.sock'
            ready_read, ready_write = os.pipe()
            broker = os.fork()
            if broker == 0:
                try:
                    os.close(ready_read)
                    os.setgid(shared_gid)
                    os.setuid(broker_uid)
                    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
                        server.bind(path)
                        os.chmod(path, 0o660)
                        server.listen(1)
                        os.write(ready_write, b'1')
                        conn, _ = server.accept()
                        with conn:
                            payload = conn.recv(4096)
                            if json.loads(payload) != {'op':'probe'}:
                                os._exit(5)
                            conn.sendall(b'{"state":"synthetic_snapshot"}\n')
                except BaseException:
                    os._exit(6)
                os._exit(0)
            os.close(ready_write)
            try:
                self.assertEqual(os.read(ready_read, 1), b'1')
                observer = os.fork()
                if observer == 0:
                    try:
                        os.setgid(shared_gid)
                        os.setuid(observer_uid)
                        install_observer_lifetime_guard()
                        result = query_verified_broker(path, broker_uid, {'op':'probe'})
                        os._exit(0 if result == {'state':'synthetic_snapshot'} else 7)
                    except BaseException:
                        os._exit(8)
                _, observer_status = os.waitpid(observer, 0)
                self.assertTrue(os.WIFEXITED(observer_status))
                self.assertEqual(os.WEXITSTATUS(observer_status), 0)
                _, broker_status = os.waitpid(broker, 0)
                broker = None
                self.assertTrue(os.WIFEXITED(broker_status))
                self.assertEqual(os.WEXITSTATUS(broker_status), 0)
            finally:
                os.close(ready_read)
                if broker is not None:
                    try:
                        os.kill(broker, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    os.waitpid(broker, 0)
