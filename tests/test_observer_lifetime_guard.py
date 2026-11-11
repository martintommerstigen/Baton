"""R25 Linux seccomp negative controls, isolated subprocesses only."""
import os
import socket
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = str(Path(__file__).resolve().parents[1])


def run_child(body):
    program = ("from remote_security.observer_lifetime_guard import *\n"
               "import errno,os,socket\n"
               "print(install_observer_lifetime_guard(), flush=True)\n" + body)
    return subprocess.run([sys.executable, "-c", program], cwd=ROOT,
                          capture_output=True, text=True, timeout=8)


@unittest.skipUnless(sys.platform.startswith("linux") and os.geteuid() != 0,
                     "dedicated non-root Linux subprocess required")
class LifetimeGuardTests(unittest.TestCase):
    def test_socket_creation_denied_both_families(self):
        r = run_child("""
for family in (socket.AF_INET,socket.AF_INET6):
    try: socket.socket(family,socket.SOCK_STREAM)
    except OSError as exc: assert exc.errno == errno.EPERM
    else: raise AssertionError('TCP socket allowed')
print('PASS')
""")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("PASS", r.stdout)

    def test_recvmsg_sendmsg_and_fd_transfer_denied(self):
        r = run_child("""
a,b=socket.socketpair()
try:
    for operation in (lambda: a.recvmsg(1), lambda: a.sendmsg([b'x'])):
        try: operation()
        except OSError as exc: assert exc.errno == errno.EPERM
        else: raise AssertionError('message syscall allowed')
    b.sendall(b'ok')
    assert a.recv(2) == b'ok'
finally: a.close();b.close()
print('PASS')
""")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("PASS", r.stdout)

    def test_guard_does_not_block_unix_connect(self):
        r = run_child("""
a,b=socket.socketpair()
a.sendall(b'a'); assert b.recv(1)==b'a'
a.close();b.close()
print('PASS')
""")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_untrusted_inherited_socket_denied_before_install(self):
        a,b=socket.socketpair()
        try:
            code="""from remote_security.observer_lifetime_guard import install_observer_lifetime_guard,LifetimeGuardDenied
try: install_observer_lifetime_guard()
except LifetimeGuardDenied: print('BLOCKED')
else: raise AssertionError('inherited socket accepted')"""
            r=subprocess.run([sys.executable,"-c",code],stdin=a,cwd=ROOT,
                             capture_output=True,text=True,timeout=8)
            self.assertEqual(r.returncode,0,r.stderr)
            self.assertIn("BLOCKED",r.stdout)
        finally:
            a.close()
            b.close()


if __name__ == "__main__":
    unittest.main()
