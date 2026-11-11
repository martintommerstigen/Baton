"""Linux-only B1/Ronja R23 integration: real kernel UIDs, no browser/UI Send.

Run as root on an isolated CI runner with pinned R23 on PYTHONPATH.
No Greg account, network listener, credential, ChatGPT login or shell endpoint.
"""
import json
import signal
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

from b1_snapshot_relay import snapshot_request

A = "11111111-1111-4111-8111-111111111111"
B = "22222222-2222-4222-8222-222222222222"
D = "a" * 64
COLLECTOR_UID = 29011
OBSERVER_UID = 29012
ADVERSARY_UID = 29014
SHARED_GID = 29013

SERVER_CODE = r'''
import sys, types
from b1_snapshot_relay import SnapshotServer
from chatgpt_ui_driver import PAUSE_FILE
A, B, D, path, observer_uid = sys.argv[1:]
class Reader:
    page = types.SimpleNamespace(url='https://chatgpt.com/c/' + A)
    def is_generating(self, source): return False
    def read_assistant_turn(self, source, turn):
        return f'BATON_WAKE {B} m-1 sha256:{D}'
with SnapshotServer(path, reader=Reader(), source_id=A,
                    allowed_targets=frozenset({B}), observer_uid=int(observer_uid), pause_checker=lambda: False) as server:
    print('READY', flush=True)
    server.serve_forever(poll_interval=0.1)
'''
CLIENT_CODE = r'''
import json, sys
from remote_security.broker_peer import query_verified_broker
from b1_snapshot_relay import snapshot_request
A, B, D, path, uid = sys.argv[1:]
print(json.dumps(query_verified_broker(path, int(uid),
      snapshot_request(A, 'turn-A', B, 'm-1', D)), sort_keys=True))
'''


@unittest.skipUnless(os.geteuid() == 0 and sys.platform.startswith('linux')
                     and shutil.which('runuser') and shutil.which('useradd'),
                     'requires isolated root Linux CI runner')
class SnapshotKernelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import remote_security.frame_credentials
            import remote_security.broker_peer
        except ImportError as exc:
            raise unittest.SkipTest('pinned Ronja R23 source unavailable') from exc
        cls.users = ['b1snapcollector', 'b1snapobserver', 'b1snapadversary']
        subprocess.run(['groupadd', '-g', str(SHARED_GID), 'b1snapgroup'], check=True)
        try:
            for name, uid in zip(cls.users, (COLLECTOR_UID, OBSERVER_UID, ADVERSARY_UID)):
                subprocess.run(['useradd', '-u', str(uid), '-g', str(SHARED_GID),
                                '-M', '-s', '/usr/sbin/nologin', name], check=True)
        except BaseException:
            for name in cls.users:
                subprocess.run(['userdel', name], stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL)
            subprocess.run(['groupdel', 'b1snapgroup'], check=False)
            raise

    @classmethod
    def tearDownClass(cls):
        for name in cls.users:
            subprocess.run(['userdel', name], stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
        subprocess.run(['groupdel', 'b1snapgroup'], check=False)

    def run_as(self, user, code, args, *, timeout=6, source_path=None):
        env = 'PYTHONPATH=' + str(source_path or os.getcwd())
        return subprocess.run(['runuser', '-u', user, '--', 'env', env,
                               sys.executable, '-c', code, *args],
                              capture_output=True, text=True, timeout=timeout)

    def test_real_kernel_snapshot_and_wrong_uid_and_restart(self):
        # GitHub runner checkout ancestors may be non-traversable by test UIDs.
        # Stage only trusted, non-secret source in a world-readable CI temp dir.
        stage = Path(tempfile.mkdtemp(prefix='b1snap-src-', dir='/tmp'))
        os.chmod(stage, 0o755)
        for name in ('b1_snapshot_relay.py', 'chatgpt_ui_driver.py',
                     'wake_adapter.py', 'wake_contract.py'):
            shutil.copy2(Path.cwd() / name, stage / name)
        (stage / 'remote_security').mkdir(mode=0o755)
        for name in ('broker_peer.py', 'frame_credentials.py', '__init__.py'):
            source = Path.cwd() / '.b5-r23' / 'remote_security' / name
            if source.exists():
                shutil.copy2(source, stage / 'remote_security' / name)
        base = Path(tempfile.mkdtemp(prefix='b1snap-', dir='/tmp'))
        os.chown(base, COLLECTOR_UID, SHARED_GID)
        os.chmod(base, 0o2750)
        path = str(base / 'snapshot.sock')
        env = 'PYTHONPATH=' + str(stage)
        cmd = ['runuser', '-u', self.users[0], '--', 'env', env, sys.executable,
               '-u', '-c', SERVER_CODE, A, B, D, path, str(OBSERVER_UID)]
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, start_new_session=True)
        try:
            for _ in range(100):
                if Path(path).exists() or proc.poll() is not None:
                    break
                time.sleep(0.05)
            if proc.poll() is not None:
                stdout, stderr = proc.communicate(timeout=2)
                self.fail('collector failed to start: stdout=' + stdout + ' stderr=' + stderr)
            self.assertTrue(Path(path).exists(), 'snapshot socket not created')
            args = [A, B, D, path, str(COLLECTOR_UID)]
            valid = self.run_as(self.users[1], CLIENT_CODE, args, source_path=stage)
            self.assertEqual(valid.returncode, 0, valid.stderr)
            data = json.loads(valid.stdout)
            self.assertEqual(data['state'], 'source_snapshot_not_authorship')
            self.assertEqual(data['origin_turn_id'], 'turn-A')
            self.assertNotIn('BATON_WAKE', valid.stdout)  # no raw turn text leaked
            # Third UID shares the Unix group but is NOT the observer.
            wrong = self.run_as(self.users[2], CLIENT_CODE, args, source_path=stage)
            self.assertNotEqual(wrong.returncode, 0)
            # No command-execution or arbitrary CDP operations.
            attack = self.run_as(self.users[1], CLIENT_CODE.replace(
                "snapshot_request(A, 'turn-A', B, 'm-1', D)",
                "{'op':'cdp','command':'Runtime.evaluate'}"), args, source_path=stage)
            self.assertNotEqual(attack.returncode, 0)
        finally:
            if proc.poll() is None:
                os.killpg(proc.pid, signal.SIGTERM)
            try:
                proc.communicate(timeout=3)
            except subprocess.TimeoutExpired:
                if proc.poll() is None:
                    os.killpg(proc.pid, signal.SIGKILL)
                proc.communicate(timeout=3)
            # A stale socket must not be silently replaced after restart.
            restart = self.run_as(self.users[0], SERVER_CODE,
                                  [A, B, D, path, str(OBSERVER_UID)], source_path=stage)
            self.assertNotEqual(restart.returncode, 0)
            Path(path).unlink(missing_ok=True)
            base.rmdir()
            shutil.rmtree(stage)


if __name__ == '__main__':
    unittest.main()
