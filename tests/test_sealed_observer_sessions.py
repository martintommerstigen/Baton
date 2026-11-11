"""R27 real Linux cross-UID kernel negatives; synthetic brokers, no browser."""
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
COLLECTOR, OBSERVER, BROKER, GROUP = 29101, 29102, 29103, 29110
APPROVED = dict(op="snapshot", source_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                origin_turn_id="turn-001", target_id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
                message_id="wake-001", payload_sha256="a" * 64)

SERVER = r"""
import hashlib,json,os,socket,sys
path=sys.argv[1]; count=int(sys.argv[2]); role=sys.argv[3]
s=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
s.bind(path);os.chmod(path,0o660);s.listen(8)
open(path+'.ready','w').close()
for _ in range(count):
 try:
  s.settimeout(5);c,_=s.accept()
 except socket.timeout:break
 with c:
  c.settimeout(5);buf=b''
  try:
   while not buf.endswith(b'\n'):
    part=c.recv(4096)
    if not part:break
    buf+=part
  except socket.timeout:pass
  if not buf:continue
  try:req=json.loads(buf)
  except Exception:continue
  if role=='snapshot':
   command=f"BATON_WAKE {req['target_id']} {req['message_id']} sha256:{req['payload_sha256']}"
   result={'state':'source_snapshot_not_authorship','source_id':req['source_id'],
           'origin_turn_id':req['origin_turn_id'],
           'source_url':'https://chatgpt.com/c/'+req['source_id'],
           'source_text_sha256':hashlib.sha256(command.encode()).hexdigest()}
  else:result={'state':'source_observation_recorded_not_authorship'}
  c.sendall((json.dumps(result)+'\n').encode())
s.close()
"""

def drop(uid):
    def fn():
        os.setgroups([])
        os.setgid(GROUP)
        os.setuid(uid)
    return fn


@unittest.skipUnless(sys.platform.startswith("linux") and os.geteuid() == 0,
                     "privileged isolated harness required for distinct real UIDs")
class R27Kernel(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="baton-r27-")
        self.addCleanup(self.tmp.cleanup)
        os.chown(self.tmp.name, COLLECTOR, GROUP)
        os.chmod(self.tmp.name, 0o710)
        for name, uid in (("collector", COLLECTOR), ("broker", BROKER)):
            directory = Path(self.tmp.name) / name
            directory.mkdir()
            os.chown(directory, uid, GROUP)
            os.chmod(directory, 0o710)
        self.snap = self.tmp.name + "/collector/snapshot.sock"
        self.witness = self.tmp.name + "/broker/witness.sock"
        self.sandbox = Path(self.tmp.name) / "code"
        package = self.sandbox / "remote_security"
        package.mkdir(parents=True)
        for name in ("sealed_observer_sessions.py", "sealed_unix_channel.py",
                     "observer_lifetime_guard.py", "observer_boundary.py"):
            shutil.copy2(ROOT / "remote_security" / name, package / name)
        os.chmod(self.sandbox, 0o755)
        os.chmod(package, 0o755)
        self.servers = []
        for path, count, uid, role in ((self.snap, 3, COLLECTOR, "snapshot"),
                                       (self.witness, 1, BROKER, "witness")):
            proc = subprocess.Popen([sys.executable, "-c", SERVER, path, str(count), role],
                                    preexec_fn=drop(uid), stdout=subprocess.DEVNULL,
                                    stderr=subprocess.PIPE, text=True)
            self.servers.append(proc)
            for _ in range(400):
                if os.path.exists(path + ".ready") or proc.poll() is not None:
                    break
                time.sleep(.02)
            self.assertTrue(os.path.exists(path + ".ready"),
                            proc.stderr.read() if proc.poll() is not None else "server not ready")
        self.addCleanup(self.stop)

    def stop(self):
        for proc in self.servers:
            if proc.poll() is None:
                proc.terminate()
            try:
                proc.communicate(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.communicate(timeout=2)

    def run_client(self, body, *, real_r25=True):
        code = "import os,socket,errno,json\nfrom remote_security.sealed_observer_sessions import *\n"
        if real_r25:
            code += ("from remote_security.observer_lifetime_guard "
                     "import install_observer_lifetime_guard\n"
                     "install_observer_lifetime_guard()\n")
        code += f"""
snap_path={self.snap!r}
witness_path={self.witness!r}
APPROVED={APPROVED!r}
snaps=[]
for _ in range(3):
 s=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);s.connect(snap_path);snaps.append(s)
w=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);w.connect(witness_path)
"""
        code += body
        return subprocess.run([sys.executable, "-c", code], cwd=self.sandbox,
                              preexec_fn=drop(OBSERVER), capture_output=True,
                              text=True, timeout=12)

    def assert_client(self, body, marker, *, real_r25=True):
        result = self.run_client(body, real_r25=real_r25)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(marker, result.stdout)

    def test_four_stream_order_and_replay(self):
        self.assert_client("""
q=seal_observer_sessions(snaps,w,snapshot_endpoint=snap_path,witness_endpoint=witness_path,collector_uid=29101,broker_uid=29103,approved_snapshot=APPROVED,pause_checker=lambda:False)
assert q.receipt=='four_role_pinned_sessions_sealed_not_host_attestation'
for f in (lambda:socket.socket(socket.AF_UNIX,socket.SOCK_STREAM),lambda:socket.socketpair()):
 try:f()
 except OSError as e:assert e.errno==errno.EPERM
 else:raise AssertionError('new socket permitted')
for _ in range(2):assert q.snapshot_query(dict(APPROVED))['state']=='source_snapshot_not_authorship'
try:q.snapshot_query(dict(APPROVED))
except SessionSealDenied:pass
else:raise AssertionError('snapshot order bypass')
witness=dict(q._witness)
assert q.witness_query(witness)['state']=='source_observation_recorded_not_authorship'
assert q.snapshot_query(dict(APPROVED))['state']=='source_snapshot_not_authorship'
try:q.witness_query(witness)
except SessionSealDenied:pass
else:raise AssertionError('witness replay')
print('ORDER_REPLAY_PASS')
""", "ORDER_REPLAY_PASS")

    def test_missing_r25_denied(self):
        self.assert_client("""
try:seal_observer_sessions(snaps,w,snapshot_endpoint=snap_path,witness_endpoint=witness_path,collector_uid=29101,broker_uid=29103,approved_snapshot=APPROVED,pause_checker=lambda:False)
except SessionSealDenied:print('R25_REQUIRED')
else:raise AssertionError('R25 bypass')
""", "R25_REQUIRED", real_r25=False)

    def test_forged_broker_uid_denied(self):
        self.assert_client("""
try:seal_observer_sessions(snaps,w,snapshot_endpoint=snap_path,witness_endpoint=witness_path,collector_uid=29101,broker_uid=29104,approved_snapshot=APPROVED,pause_checker=lambda:False)
except SessionSealDenied:print('UID_DENIED')
else:raise AssertionError('UID spoof')
""", "UID_DENIED")

    def test_extra_socket_denied(self):
        self.assert_client("""
a,b=socket.socketpair()
try:seal_observer_sessions(snaps,w,snapshot_endpoint=snap_path,witness_endpoint=witness_path,collector_uid=29101,broker_uid=29103,approved_snapshot=APPROVED,pause_checker=lambda:False)
except SessionSealDenied:print('EXTRA_SOCKET_DENIED')
else:raise AssertionError('inherited socket')
""", "EXTRA_SOCKET_DENIED")

    def test_pause_and_payload_denied(self):
        self.assert_client("""
try:seal_observer_sessions(snaps,w,snapshot_endpoint=snap_path,witness_endpoint=witness_path,collector_uid=29101,broker_uid=29103,approved_snapshot=APPROVED,pause_checker=lambda:True)
except SessionSealDenied:pass
else:raise AssertionError('pause bypass')
q=seal_observer_sessions(snaps,w,snapshot_endpoint=snap_path,witness_endpoint=witness_path,collector_uid=29101,broker_uid=29103,approved_snapshot=APPROVED,pause_checker=lambda:False)
wrong=dict(APPROVED);wrong['payload_sha256']='b'*64
try:q.snapshot_query(wrong)
except SessionSealDenied:print('PAUSE_PAYLOAD_DENIED')
else:raise AssertionError('payload mismatch')
""", "PAUSE_PAYLOAD_DENIED")

    def test_witness_disconnect_uncertain_no_retry(self):
        self.assert_client("""
q=seal_observer_sessions(snaps,w,snapshot_endpoint=snap_path,witness_endpoint=witness_path,collector_uid=29101,broker_uid=29103,approved_snapshot=APPROVED,pause_checker=lambda:False)
for _ in range(2):q.snapshot_query(dict(APPROVED))
w.close()
try:q.witness_query(dict(q._witness))
except SessionUncertain:pass
else:raise AssertionError('uncertain witness accepted')
try:q.witness_query(dict(q._witness))
except SessionSealDenied:print('NO_RETRY_PASS')
else:raise AssertionError('blind retry')
""", "NO_RETRY_PASS")

    def test_path_traversal_denied(self):
        self.assert_client("""
try:seal_observer_sessions(snaps,w,snapshot_endpoint=snap_path+'/../snapshot.sock',witness_endpoint=witness_path,collector_uid=29101,broker_uid=29103,approved_snapshot=APPROVED,pause_checker=lambda:False)
except SessionSealDenied:print('PATH_DENIED')
else:raise AssertionError('path traversal')
""", "PATH_DENIED")


if __name__ == "__main__":
    unittest.main()
