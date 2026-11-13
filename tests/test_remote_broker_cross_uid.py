"""Optional root-only isolated real UID integration (skipped in hosted non-root CI)."""
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest


@unittest.skipUnless(os.name == 'posix' and os.geteuid() == 0 and
                     Path('/usr/bin/setpriv').exists(), 'requires isolated Linux root with setpriv')
class RealUIDBrokerTest(unittest.TestCase):
    def test_separate_uid_auth_and_impostor(self):
        # nobody is broker, oai is client; group 1000 has search/write access.
        broker_uid, client_uid, group = 65534, 1000, 1000
        with tempfile.TemporaryDirectory(prefix='baton-b5-') as tmp:
            parent = Path(tmp)
            os.chown(parent, broker_uid, group)
            parent.chmod(0o750)
            sock = parent / 'broker.sock'
            script = ("import os,socket,sys; p=sys.argv[1]; "
                      "s=socket.socket(socket.AF_UNIX); s.bind(p); "
                      "os.chmod(p,0o660); s.listen(2); "
                      "c,_=s.accept(); b=c.recv(8192); "
                      "c.sendall(b'{\"state\":\"ready\"}\\n'); c.close(); s.close()")
            proc = subprocess.Popen(['setpriv','--reuid',str(broker_uid),'--regid',str(group),
                                     '--clear-groups',sys.executable,'-c',script,str(sock)],
                                    stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            try:
                for _ in range(100):
                    if sock.exists(): break
                    time.sleep(0.01)
                self.assertTrue(sock.exists(), 'broker failed to bind')
                client = ("from remote_security.broker_peer import query_verified_broker; "
                          "import sys; print(query_verified_broker(sys.argv[1],65534,{'op':'status'}))")
                env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1]))
                result = subprocess.run(['setpriv','--reuid',str(client_uid),'--regid',str(group),
                                         '--clear-groups',sys.executable,'-c',client,str(sock)],
                                        env=env,capture_output=True,text=True,timeout=5)
                self.assertEqual(result.returncode,0,result.stderr)
                self.assertIn("'state': 'ready'",result.stdout)
                proc.wait(timeout=3)
                self.assertEqual(proc.returncode,0,proc.stderr.read().decode())
                # Root simulates an inode swap; a B-owned fake socket must fail.
                sock.unlink()
                fake = socket.socket(socket.AF_UNIX)
                try:
                    fake.bind(str(sock)); os.chown(sock,client_uid,group)
                    fake.listen(1)
                    result = subprocess.run(['setpriv','--reuid',str(client_uid),'--regid',str(group),
                                             '--clear-groups',sys.executable,'-c',client,str(sock)],
                                            env=env,capture_output=True,text=True,timeout=5)
                    self.assertNotEqual(result.returncode,0)
                    self.assertIn('UntrustedBroker',result.stderr)
                    fake.settimeout(0.2)
                    with self.assertRaises(socket.timeout):
                        fake.accept()  # rejected before even connecting to the impostor
                finally:
                    fake.close()
            finally:
                if proc.poll() is None:
                    proc.terminate(); proc.wait(timeout=3)
                parent.chmod(0o750)
                proc.stdout.close(); proc.stderr.close()

if __name__ == '__main__': unittest.main()
