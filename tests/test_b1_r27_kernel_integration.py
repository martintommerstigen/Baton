"""H26 B1+R27 real Linux-UID/seccomp integration; synthetic ChatGPT source.

The R27 test harness is copied from Ronja's pinned source in CI. Nothing
contacts Greg or ChatGPT. The test uses four actual Linux process UIDs.
"""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
try:
    from test_sealed_observer_sessions import R27Kernel, OBSERVER, drop
except ImportError:
    R27Kernel = None

CLIENT = r'''
import errno,json,socket
from b1_snapshot_relay import SnapshotUncertain
from run_b1_r27_sealed_observer import run_sealed_observation
from remote_security.observer_lifetime_guard import install_observer_lifetime_guard
from remote_security.sealed_unix_channel import _check_path
from remote_security.sealed_observer_sessions import seal_observer_sessions

args=dict(source='aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
          source_turn_id='turn-001', target='bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb',
          message_id='wake-001',payload_sha256='a'*64,
          snapshot_socket=SNAP,broker_socket=WITNESS,
          collector_uid=29101,broker_uid=29103,
          pause_checker=lambda:False,
          preflight=lambda:{'status':'scoped_preflight_pass_not_attestation'},
          install_guard=install_observer_lifetime_guard,
          check_endpoint=_check_path,sealer=seal_observer_sessions)
if MODE=='uncertain':
    def interrupted(*a,**kw):
        sealed=seal_observer_sessions(*a,**kw)
        class Interrupted:
            receipt=sealed.receipt
            snapshot_query=sealed.snapshot_query
            def witness_query(self,req):
                sealed._streams[3].close()
                return sealed.witness_query(req)
        return Interrupted()
    args['sealer']=interrupted
    try:run_sealed_observation(**args)
    except SnapshotUncertain:print('UNCERTAIN_NO_RETRY')
    else:raise AssertionError('witness failure accepted')
else:
    result=run_sealed_observation(**args)
    assert result=={'state':'source_observation_recorded_not_authorship',
                    'classification':'snapshot_observation_not_chatgpt_authorship'},result
    print('B1_R27_OBSERVATION_ONLY')
try:socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
except OSError as exc:assert exc.errno==errno.EPERM
else:raise AssertionError('post-seal socket creation permitted')
'''


@unittest.skipUnless(R27Kernel is not None and sys.platform.startswith('linux')
                     and os.geteuid()==0, 'pinned R27 privileged harness required')
class B1R27Kernel(unittest.TestCase):
    def setUp(self):
        R27Kernel.setUp(self)
        for name in ('run_b1_r27_sealed_observer.py','run_b1_snapshot_observer.py',
                     'b1_snapshot_relay.py','chatgpt_ui_driver.py',
                     'wake_adapter.py','wake_contract.py'):
            shutil.copy2(ROOT/name,self.sandbox/name)
            os.chmod(self.sandbox/name,0o644)

    def run_mode(self,mode):
        script=f'SNAP={self.snap!r}\nWITNESS={self.witness!r}\nMODE={mode!r}\n'+CLIENT
        return subprocess.run([sys.executable,'-c',script],cwd=self.sandbox,
                              preexec_fn=drop(OBSERVER),capture_output=True,
                              text=True,timeout=12)

    def test_real_kernel_four_uid_b1_observation(self):
        result=self.run_mode('success')
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('B1_R27_OBSERVATION_ONLY',result.stdout)

    def test_witness_disconnect_uncertain_not_verified(self):
        result=self.run_mode('uncertain')
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('UNCERTAIN_NO_RETRY',result.stdout)


if __name__=='__main__':unittest.main()
