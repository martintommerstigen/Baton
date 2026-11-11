"""Trusted-runner kernel probe test: distinct real Linux UIDs, zero payload."""
import json
import os
from pathlib import Path
import socket
import tempfile
import unittest

from remote_security.source_broker_probe import probe

SERVICE_UID = 21001
CLIENT_UID = 21003
SHARED_GID = 21002


@unittest.skipUnless(os.name == 'posix' and os.geteuid() == 0
                     and hasattr(os, 'fork') and hasattr(socket, 'SO_PEERCRED'),
                     'trusted root-only kernel test')
class RealUidProbe(unittest.TestCase):
    def test_real_peer_uid_and_no_request_bytes(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            base.chmod(0o755)
            parent = base / 'socketdir'
            parent.mkdir()
            os.chown(parent, SERVICE_UID, SHARED_GID)
            parent.chmod(0o710)
            path = parent / 'source.sock'
            ready_r, ready_w = os.pipe()
            data_r, data_w = os.pipe()
            pid = os.fork()
            if pid == 0:
                try:
                    os.close(ready_r)
                    os.close(data_r)
                    os.setgid(SHARED_GID)
                    os.setuid(SERVICE_UID)
                    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
                        server.bind(str(path))
                        path.chmod(0o660)
                        server.listen(1)
                        server.settimeout(5)
                        os.write(ready_w, b'R')
                        with server.accept()[0] as conn:
                            conn.settimeout(3)
                            payload = conn.recv(4096)
                            os.write(data_w, str(len(payload)).encode())
                    os._exit(0)
                except BaseException:
                    os.write(ready_w, b'E')
                    os._exit(3)
            os.close(ready_w)
            os.close(data_w)
            try:
                self.assertEqual(os.read(ready_r, 1), b'R')
                result_r, result_w = os.pipe()
                caller = os.fork()
                if caller == 0:
                    try:
                        os.close(result_r)
                        os.setgid(SHARED_GID)
                        os.setuid(CLIENT_UID)
                        result = probe(str(path), SERVICE_UID, connect=True)
                        os.write(result_w, json.dumps(result).encode())
                        os._exit(0)
                    except BaseException:
                        os._exit(3)
                os.close(result_w)
                result = os.read(result_r, 4096)
                os.close(result_r)
                _, caller_status = os.waitpid(caller, 0)
                self.assertEqual(os.waitstatus_to_exitcode(caller_status), 0)
                receipt = json.loads(result)
                self.assertEqual(receipt['state'], 'kernel_peer_uid_verified_no_request')
                self.assertTrue(receipt['peer_uid_verified'])
                self.assertEqual(receipt['request_bytes_sent'], 0)
                self.assertEqual(os.read(data_r, 16), b'0')
                _, server_status = os.waitpid(pid, 0)
                pid = None
                self.assertEqual(os.waitstatus_to_exitcode(server_status), 0)
            finally:
                os.close(ready_r)
                os.close(data_r)
                if pid is not None:
                    try:
                        os.kill(pid, 9)
                    except ProcessLookupError:
                        pass
                    os.waitpid(pid, 0)


if __name__ == '__main__':
    unittest.main()
