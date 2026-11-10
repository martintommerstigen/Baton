"""B5 deterministic TOCTOU: pathname swaps after stat, before connect.

Real broker UID 65534, client UID 1000, forged listener UID 0. The fake
listener's socket inode is CHOWNed to the expected UID, but SO_PEERCRED
must still reject its actual process UID before any request bytes leave.
Requires an isolated root Linux runner; hosted non-root CI skips.
"""
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest


@unittest.skipUnless(sys.platform.startswith('linux') and os.geteuid() == 0 and
                     Path('/usr/bin/setpriv').exists(), 'isolated root/setpriv Linux only')
class SocketSwapRealUIDTest(unittest.TestCase):
    def test_swap_between_lstat_and_connect_never_discloses_request(self):
        broker_uid, client_uid, group = 65534, 1000, 1000
        with tempfile.TemporaryDirectory(prefix='baton-b5-swap-') as tmp:
            parent = Path(tmp)
            os.chown(parent, broker_uid, group)
            parent.chmod(0o750)
            path = parent / 'broker.sock'
            original = parent / 'original.sock'
            broker_script = (
                'import os,socket,sys,time; s=socket.socket(socket.AF_UNIX); '
                's.bind(sys.argv[1]); os.chmod(sys.argv[1],0o660); '
                's.listen(1); time.sleep(5); s.close()'
            )
            broker = subprocess.Popen(
                ['/usr/bin/setpriv', '--reuid', str(broker_uid), '--regid', str(group),
                 '--clear-groups', sys.executable, '-c', broker_script, str(path)],
                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            fake = None
            client = None
            try:
                for _ in range(100):
                    if path.exists():
                        break
                    time.sleep(0.01)
                self.assertTrue(path.exists(), 'real broker failed to bind')
                client_script = '''
import sys
from remote_security import broker_peer as p
orig = p._checked_socket_path
def checkpoint(path, uid):
    checked = orig(path, uid)
    print('CHECKED', flush=True)
    if sys.stdin.readline() != 'SWAPPED\\n':
        raise RuntimeError('swap handshake missing')
    return checked
p._checked_socket_path = checkpoint
p.query_verified_broker(sys.argv[1], 65534, {'op':'admit','payload':'never-disclose'})
'''
                env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1]))
                client = subprocess.Popen(
                    ['/usr/bin/setpriv', '--reuid', str(client_uid), '--regid', str(group),
                     '--clear-groups', sys.executable, '-c', client_script, str(path)],
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE, text=True, env=env)
                self.assertEqual(client.stdout.readline().strip(), 'CHECKED')
                path.rename(original)
                fake = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                fake.bind(str(path))
                os.chown(path, broker_uid, group)  # spoof original socket owner
                os.chmod(path, 0o660)
                fake.listen(1)
                seen = []
                def observe():
                    fake.settimeout(3)
                    try:
                        conn, _ = fake.accept()
                        with conn:
                            conn.settimeout(2)
                            seen.append(conn.recv(8192))
                    except OSError as exc:
                        seen.append(('socket_error', type(exc).__name__))
                observer = threading.Thread(target=observe, daemon=True)
                observer.start()
                client.stdin.write('SWAPPED\n')
                client.stdin.flush()
                client.stdin.close()
                client.wait(timeout=5)
                observer.join(4)
                self.assertNotEqual(client.returncode, 0)
                self.assertIn('UntrustedBroker', client.stderr.read())
                self.assertEqual(seen, [b''], 'forged peer received request bytes')
            finally:
                if client is not None and client.poll() is None:
                    client.kill(); client.wait(timeout=3)
                if broker.poll() is None:
                    broker.terminate(); broker.wait(timeout=3)
                if fake is not None:
                    fake.close()
                if client is not None:
                    client.stdout.close(); client.stderr.close()
                broker.stderr.close()


if __name__ == '__main__':
    unittest.main()
