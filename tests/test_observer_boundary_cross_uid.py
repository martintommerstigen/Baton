"""Trusted isolated Linux runner: actual UID separation, never a Greg test."""
import os
import signal
import sys
import tempfile
import time
import unittest
from pathlib import Path

from remote_security.observer_boundary import BoundaryDenied, _profile_denied, audit_observer_boundary


@unittest.skipUnless(sys.platform.startswith('linux') and os.geteuid() == 0,
                     'isolated root Linux CI only')
class RealKernelBoundaryTests(unittest.TestCase):
    def test_actual_profile_denial_and_same_netns_rejection(self):
        collector_uid, observer_uid = 29101, 29102
        with tempfile.TemporaryDirectory(prefix='b5-r24-', dir='/tmp') as d:
            os.chmod(d, 0o755)
            profile = str(Path(d) / 'profile')
            os.mkdir(profile, 0o700)
            os.chown(profile, collector_uid, collector_uid)
            readfd, writefd = os.pipe()
            collector = os.fork()
            if collector == 0:
                try:
                    os.close(readfd)
                    os.setgid(collector_uid)
                    os.setuid(collector_uid)
                    fd = os.open(profile, os.O_RDONLY | os.O_DIRECTORY)
                    os.close(fd)  # Actual collector can read its profile.
                    os.write(writefd, b'1')
                    time.sleep(8)
                except BaseException:
                    os._exit(2)
                os._exit(0)
            os.close(writefd)
            try:
                self.assertEqual(os.read(readfd, 1), b'1')
                observer = os.fork()
                if observer == 0:
                    try:
                        os.setgid(observer_uid)
                        os.setuid(observer_uid)
                        _profile_denied(profile)  # Real EACCES, not a mock.
                        try:
                            audit_observer_boundary(collector_pid=collector,
                                collector_uid=collector_uid, profile=profile,
                                snapshot_socket=str(Path(d) / 'unused.sock'))
                        except BoundaryDenied as exc:
                            os._exit(0 if 'network isolation not established' in str(exc) else 3)
                        os._exit(4)
                    except BaseException:
                        os._exit(5)
                _, status = os.waitpid(observer, 0)
                self.assertTrue(os.WIFEXITED(status))
                self.assertEqual(os.WEXITSTATUS(status), 0)
            finally:
                os.close(readfd)
                try:
                    os.kill(collector, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                os.waitpid(collector, 0)


if __name__ == '__main__':
    unittest.main()
