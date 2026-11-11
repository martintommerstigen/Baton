"""R25 second-pass seccomp persistence and pidfd negatives."""
import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = str(Path(__file__).resolve().parents[1])


def isolated(body):
    code = ("from remote_security.observer_lifetime_guard import install_observer_lifetime_guard\n"
            "install_observer_lifetime_guard()\n" + body)
    return subprocess.run([sys.executable, "-c", code], cwd=ROOT,
                          capture_output=True, text=True, timeout=8)


@unittest.skipUnless(sys.platform.startswith("linux") and os.geteuid() != 0,
                     "non-root Linux seccomp required")
class LifetimePersistenceTests(unittest.TestCase):
    def test_pidfd_getfd_denied_by_kernel(self):
        r = isolated("""
import ctypes,errno
lib=ctypes.CDLL('libseccomp.so.2')
lib.seccomp_syscall_resolve_name.argtypes=[ctypes.c_char_p]
lib.seccomp_syscall_resolve_name.restype=ctypes.c_int
number=lib.seccomp_syscall_resolve_name(b'pidfd_getfd')
assert number >= 0
libc=ctypes.CDLL(None,use_errno=True)
libc.syscall.restype=ctypes.c_long
assert libc.syscall(number,-1,-1,0)==-1
assert ctypes.get_errno()==errno.EPERM
print('PASS')
""")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("PASS", r.stdout)

    def test_filter_persists_across_exec(self):
        r = isolated("""
import os,sys
os.execv(sys.executable,[sys.executable,'-c',
    "import socket,errno;\\n"
    "try: socket.socket(socket.AF_INET,socket.SOCK_STREAM)\\n"
    "except OSError as e: assert e.errno==errno.EPERM\\n"
    "else: raise AssertionError('exec bypass')\\n"
    "print('PASS')"])
""")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("PASS", r.stdout)


    def test_unlisted_unix_endpoint_remains_reachable_negative(self):
        """Known limitation: syscall filter does not allowlist AF_UNIX paths."""
        r = isolated("""
import socket,tempfile
with tempfile.TemporaryDirectory() as directory:
    path=directory+'/undeclared.sock'
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as listener:
        listener.bind(path); listener.listen(1)
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as client:
            client.connect(path)
            peer,_=listener.accept()
            with peer:
                client.sendall(b'x')
                assert peer.recv(1)==b'x'
print('NEGATIVE: undeclared Unix path reachable')
""")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("undeclared Unix path reachable", r.stdout)

if __name__ == "__main__":
    unittest.main()
