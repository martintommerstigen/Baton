"""R26 kernel negatives with synthetic R25 prerequisite; no Greg/CDP/UI."""
import ctypes
import importlib.util
import errno
import os
import shutil
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
BROKER_UID, OBS_UID, GROUP = 29101, 29102, 29110

PREREQ = '''
import ctypes,errno,socket
class Cmp(ctypes.Structure):
 _fields_=[('arg',ctypes.c_uint),('op',ctypes.c_uint),('datum_a',ctypes.c_uint64),('datum_b',ctypes.c_uint64)]
lib=ctypes.CDLL('libseccomp.so.2',use_errno=True)
lib.seccomp_init.argtypes=[ctypes.c_uint32];lib.seccomp_init.restype=ctypes.c_void_p
lib.seccomp_syscall_resolve_name.argtypes=[ctypes.c_char_p];lib.seccomp_syscall_resolve_name.restype=ctypes.c_int
lib.seccomp_rule_add_array.argtypes=[ctypes.c_void_p,ctypes.c_uint32,ctypes.c_int,ctypes.c_uint,ctypes.POINTER(Cmp)];lib.seccomp_rule_add_array.restype=ctypes.c_int
lib.seccomp_load.argtypes=[ctypes.c_void_p];lib.seccomp_load.restype=ctypes.c_int
lib.seccomp_release.argtypes=[ctypes.c_void_p]
ctx=lib.seccomp_init(0x7fff0000)
for name in ('recvmsg','sendmsg'):
 assert lib.seccomp_rule_add_array(ctx,0x00050000|errno.EPERM,lib.seccomp_syscall_resolve_name(name.encode()),0,None)==0
for family in (socket.AF_INET,socket.AF_INET6):
 c=Cmp(0,4,family,0)
 assert lib.seccomp_rule_add_array(ctx,0x00050000|errno.EPERM,lib.seccomp_syscall_resolve_name(b'socket'),1,ctypes.byref(c))==0
libc=ctypes.CDLL(None);libc.prctl.argtypes=[ctypes.c_int,ctypes.c_ulong,ctypes.c_ulong,ctypes.c_ulong,ctypes.c_ulong]
assert libc.prctl(38,1,0,0,0)==0
assert lib.seccomp_load(ctx)==0
lib.seccomp_release(ctx)
'''
SERVER = '''
import os,socket,sys
path=sys.argv[1];s=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);s.bind(path);os.chmod(path,0o660);s.listen(3)
u=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);u.bind(path.replace('snapshot.sock','undeclared.sock'));os.chmod(path.replace('snapshot.sock','undeclared.sock'),0o660);u.listen(2)
open(path+'.ready','w').close()
for i in range(3):
 s.settimeout(5)
 try: c,_=s.accept()
 except socket.timeout: break
 with c:
  while True:
   b=c.recv(64)
   if not b:break
   c.sendall(b'echo:'+b)
s.close();u.close()
'''

def drop(uid):
    def fn():
        os.setgroups([])
        os.setgid(GROUP)
        os.setuid(uid)
    return fn

@unittest.skipUnless(sys.platform.startswith('linux') and os.geteuid()==0,
                     'root harness needed for independent real Linux UIDs')
class SealedCrossUid(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='baton-r26-')
        self.addCleanup(self.tmp.cleanup)
        self.path=self.tmp.name+'/snapshot.sock'
        os.chown(self.tmp.name,BROKER_UID,GROUP)
        os.chmod(self.tmp.name,0o710)
        # After setuid, CI checkout parents may be inaccessible (GitHub runner).
        # Copy only pinned source modules to a group-traversable test sandbox.
        self.sandbox=Path(self.tmp.name)/'code'
        package=self.sandbox/'remote_security'
        package.mkdir(parents=True)
        for name in ('sealed_unix_channel.py','observer_lifetime_guard.py',
                     'observer_boundary.py'):
            source=ROOT/'remote_security'/name
            if source.exists():
                shutil.copy2(source,package/name)
        os.chmod(self.sandbox,0o755)
        os.chmod(package,0o755)
        self.server=subprocess.Popen([sys.executable,'-c',SERVER,self.path],
            preexec_fn=drop(BROKER_UID),stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        self.addCleanup(self.stop)
        for _ in range(100):
            if os.path.exists(self.path+'.ready'):break
            if self.server.poll() is not None:break
            time.sleep(.02)
        self.assertTrue(os.path.exists(self.path+'.ready'),self.server.stderr.read() if self.server.poll() is not None else 'no ready')

    def stop(self):
        if self.server.poll() is None:
            self.server.terminate()
            try:self.server.wait(timeout=2)
            except subprocess.TimeoutExpired:self.server.kill()
        self.server.communicate(timeout=2)

    def client(self, body, *, prerequisite=True, real_r25=False):
        code='import os,socket,errno,sys\nfrom remote_security.sealed_unix_channel import *\n'
        if real_r25:
            code+="from remote_security.observer_lifetime_guard import install_observer_lifetime_guard\ninstall_observer_lifetime_guard()\n"
        elif prerequisite:code+=PREREQ
        code+=f'path={self.path!r}\n'
        code+='s=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);s.connect(path)\n'
        code+=body
        return subprocess.run([sys.executable,'-c',code],cwd=self.sandbox,
            preexec_fn=drop(OBS_UID),capture_output=True,text=True,timeout=10)

    def test_preconnected_channel_survives_but_new_connections_denied(self):
        r=self.client('''
assert seal_unix_channel(s,endpoint=path,peer_uid=29101)=='single_unix_channel_sealed_not_host_attestation'
s.sendall(b'ping');assert s.recv(64)==b'echo:ping'
for op in (lambda:socket.socket(socket.AF_UNIX,socket.SOCK_STREAM),lambda:socket.socketpair()):
 try:op()
 except OSError as e:assert e.errno==errno.EPERM
 else:raise AssertionError('new socket permitted')
print('SEALED_KERNEL_PASS')
''')
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertIn('SEALED_KERNEL_PASS',r.stdout)

    def test_same_group_undeclared_unix_endpoint_access_revoked(self):
        r=self.client('''
other=path.replace('snapshot.sock','undeclared.sock')
probe=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
probe.connect(other)  # reachable under same group BEFORE the seal
probe.close()
seal_unix_channel(s,endpoint=path,peer_uid=29101)
try:
 probe=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
except OSError as e:assert e.errno==errno.EPERM
else:
 probe.close()
 raise AssertionError('undeclared endpoint still reachable')
s.sendall(b'allowed');assert s.recv(64)==b'echo:allowed'
print('UNDECLARED_ENDPOINT_DENIED')
''')
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertIn('UNDECLARED_ENDPOINT_DENIED',r.stdout)

    def test_no_r25_kernel_prerequisite_fails_closed(self):
        r=self.client('''
try:seal_unix_channel(s,endpoint=path,peer_uid=29101)
except ChannelSealDenied:print('R25_REQUIRED')
else:raise AssertionError('R25 bypass')
''',prerequisite=False)
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertIn('R25_REQUIRED',r.stdout)

    def test_wrong_peer_uid_fails_closed(self):
        r=self.client('''
try:seal_unix_channel(s,endpoint=path,peer_uid=29103)
except ChannelSealDenied:print('WRONG_UID_BLOCKED')
else:raise AssertionError('UID spoof')
''')
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertIn('WRONG_UID_BLOCKED',r.stdout)

    def test_extra_inherited_unix_socket_fails_closed(self):
        r=self.client('''
a,b=socket.socketpair()
try:
 try:seal_unix_channel(s,endpoint=path,peer_uid=29101)
 except ChannelSealDenied:print('INHERITED_BLOCKED')
 else:raise AssertionError('extra FD accepted')
finally:a.close();b.close()
''')
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertIn('INHERITED_BLOCKED',r.stdout)

    def test_path_alias_or_traversal_denied(self):
        r=self.client('''
for p in (path.replace('/snapshot.sock','/../snapshot.sock'),path.replace('/snapshot.sock','//snapshot.sock')):
 try:seal_unix_channel(s,endpoint=p,peer_uid=29101)
 except ChannelSealDenied:pass
 else:raise AssertionError('alias accepted')
print('PATH_BLOCKED')
''')
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertIn('PATH_BLOCKED',r.stdout)

    def test_forged_socket_file_owner_does_not_spoof_peer_uid(self):
        # Root changes the *pathname* owner; SO_PEERCRED still reports 29101.
        os.chown(self.path, 29103, GROUP)
        r=self.client('''
try:seal_unix_channel(s,endpoint=path,peer_uid=29103)
except ChannelSealDenied:print('FORGED_OWNER_BLOCKED')
else:raise AssertionError('pathname ownership spoof accepted')
''')
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertIn('FORGED_OWNER_BLOCKED',r.stdout)

    def test_symlinked_parent_rejected_even_if_target_is_valid(self):
        alias=self.tmp.name+'-alias'
        os.symlink(self.tmp.name,alias)
        self.addCleanup(lambda:os.unlink(alias))
        r=self.client('''
from remote_security.sealed_unix_channel import _check_path
try:_check_path(path.replace('snapshot.sock','../snapshot.sock'),29101)
except ChannelSealDenied:pass
else:raise AssertionError('traversal accepted')
print('DIRECT_PATH_GUARD_PASS')
''')
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertIn('DIRECT_PATH_GUARD_PASS',r.stdout)
        # Actual symlink path is checked without attempting a new connection.
        code='from remote_security.sealed_unix_channel import _check_path,ChannelSealDenied\ntry:_check_path('+repr(alias+'/snapshot.sock')+',29101)\nexcept ChannelSealDenied:print("SYMLINK_BLOCKED")\nelse:raise AssertionError("symlink accepted")'
        t=subprocess.run([sys.executable,'-c',code],cwd=self.sandbox,preexec_fn=drop(OBS_UID),capture_output=True,text=True,timeout=8)
        self.assertEqual(t.returncode,0,t.stderr)
        self.assertIn('SYMLINK_BLOCKED',t.stdout)

    @unittest.skipUnless(importlib.util.find_spec('remote_security.observer_lifetime_guard'),
                         'pinned R25 dependency not present in standalone test workspace')
    def test_real_pinned_r25_then_r26_kernel_chain(self):
        r=self.client('''
assert seal_unix_channel(s,endpoint=path,peer_uid=29101)=='single_unix_channel_sealed_not_host_attestation'
s.sendall(b'actual');assert s.recv(64)==b'echo:actual'
try:socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
except OSError as e:assert e.errno==errno.EPERM
else:raise AssertionError('undeclared Unix endpoint still accessible')
print('REAL_R25_R26_PASS')
''',prerequisite=False,real_r25=True)
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertIn('REAL_R25_R26_PASS',r.stdout)

    def test_seccomp_persists_after_exec(self):
        r=self.client('''
seal_unix_channel(s,endpoint=path,peer_uid=29101)
s.set_inheritable(True)
code="import socket,errno,sys;s=socket.socket(fileno=int(sys.argv[1]));s.sendall(b'exec');assert s.recv(64)==b'echo:exec';\\ntry:socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)\\nexcept OSError as e:assert e.errno==errno.EPERM\\nelse:raise AssertionError('filter lost')\\nprint('EXEC_FILTER_PASS')".replace('\\\\n','\\n')
os.execv(sys.executable,[sys.executable,'-c',code,str(s.fileno())])
''')
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertIn('EXEC_FILTER_PASS',r.stdout)

if __name__=='__main__':unittest.main()
