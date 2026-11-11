"""B1 H24: enforce Ronja R25 lifetime guard in the direct B1 entry point.

Synthetic source, no Greg, CDP, UI Send, token or live A->B->C.
Kernel subprocess test uses actual Linux seccomp only on a non-root runner.
"""
import contextlib
import errno
import io
import os
import subprocess
import sys
import textwrap
import types
import unittest
from unittest import mock

import run_b1_snapshot_observer as b1

RECEIPT = "lifetime_guard_loaded_not_host_attestation"


def valid_args():
    uid = os.geteuid()
    return [
        "--source", "11111111-1111-4111-8111-111111111111",
        "--source-turn-id", "turn-A",
        "--target", "22222222-2222-4222-8222-222222222222",
        "--id", "m-1",
        "--payload-sha256", "a" * 64,
        "--snapshot-socket", "/tmp/b1-h24-snapshot-nonexistent.sock",
        "--collector-uid", str(uid + 1000),
        "--collector-pid", "1234",
        "--browser-profile", "/tmp/b1-h24-profile-nonexistent",
        "--broker-socket", "/tmp/b1-h24-broker-nonexistent.sock",
        "--broker-uid", str(uid + 1001),
    ]


class LifetimeEntryContract(unittest.TestCase):
    def test_exact_r25_receipt_accepted_without_claiming_attestation(self):
        installer = mock.Mock(return_value=RECEIPT)
        self.assertEqual(b1.require_lifetime_guard(installer), RECEIPT)
        installer.assert_called_once_with()

    def test_missing_or_forged_receipt_denied(self):
        for receipt in (None, True, {}, "verified", "scoped_preflight_pass_not_attestation"):
            with self.subTest(receipt=receipt), self.assertRaises(PermissionError):
                b1.require_lifetime_guard(lambda: receipt)

    def test_missing_installer_is_not_silent_fallback(self):
        with mock.patch.dict(sys.modules, {"remote_security.observer_lifetime_guard": None}):
            with self.assertRaisesRegex(PermissionError, "unavailable"):
                b1.require_lifetime_guard()

    def test_installer_failure_not_retried(self):
        installer = mock.Mock(side_effect=PermissionError("kernel refused seccomp"))
        with self.assertRaisesRegex(PermissionError, "seccomp"):
            b1.require_lifetime_guard(installer)
        installer.assert_called_once_with()

    def test_direct_main_denies_before_preflight_and_observation(self):
        with (mock.patch.object(b1, "require_lifetime_guard",
                                side_effect=PermissionError("R25 unavailable")) as guard,
              mock.patch.object(b1, "enforce_scoped_boundary") as boundary,
              mock.patch.object(b1, "observe_via_snapshots") as observe):
            with self.assertRaisesRegex(PermissionError, "R25 unavailable"):
                b1.main(valid_args())
            guard.assert_called_once_with()
            boundary.assert_not_called()
            observe.assert_not_called()

    def test_direct_main_guard_precedes_r24_and_source(self):
        calls = []
        peer = types.ModuleType("remote_security.broker_peer")
        peer.query_verified_broker = lambda *args, **kwargs: None
        def lifetime():
            calls.append("r25")
            return RECEIPT
        def boundary(**kwargs):
            calls.append("r24")
            return {"status": "scoped_preflight_pass_not_attestation"}
        def observe(**kwargs):
            calls.append("observe")
            return {"state": "synthetic_source_only"}
        with (mock.patch.dict(sys.modules, {"remote_security.broker_peer": peer}),
              mock.patch.object(b1, "require_lifetime_guard", side_effect=lifetime),
              mock.patch.object(b1, "enforce_scoped_boundary", side_effect=boundary),
              mock.patch.object(b1, "observe_via_snapshots", side_effect=observe),
              mock.patch.object(b1, "pause_active", return_value=False),
              contextlib.redirect_stdout(io.StringIO())):
            b1.main(valid_args())
        self.assertEqual(calls, ["r25", "r24", "observe"])

    def test_direct_main_r24_denial_after_r25_stops_observation(self):
        peer = types.ModuleType("remote_security.broker_peer")
        peer.query_verified_broker = lambda *args, **kwargs: None
        with (mock.patch.dict(sys.modules, {"remote_security.broker_peer": peer}),
              mock.patch.object(b1, "require_lifetime_guard", return_value=RECEIPT),
              mock.patch.object(b1, "enforce_scoped_boundary",
                                side_effect=PermissionError("R24 denied")),
              mock.patch.object(b1, "observe_via_snapshots") as observe,
              mock.patch.object(b1, "pause_active", return_value=False)):
            with self.assertRaisesRegex(PermissionError, "R24 denied"):
                b1.main(valid_args())
            observe.assert_not_called()


class ActualKernelGate(unittest.TestCase):
    @unittest.skipUnless(sys.platform.startswith("linux") and os.geteuid() != 0,
                         "requires non-root Linux and pinned Ronja R25")
    def test_ronja_launcher_then_direct_b1_guard_is_safe(self):
        # Ronja's launcher loads R25 before importing B1 main; H24 main
        # installs R25 again. Verify this composition on the actual kernel.
        code = textwrap.dedent("""
            import errno
            import socket
            from run_b1_snapshot_observer import require_lifetime_guard
            assert require_lifetime_guard() == "lifetime_guard_loaded_not_host_attestation"
            assert require_lifetime_guard() == "lifetime_guard_loaded_not_host_attestation"
            try:
                socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            except OSError as exc:
                assert exc.errno == errno.EPERM
            else:
                raise AssertionError("double guard lost restriction")
            print("B1_R25_DOUBLE_INSTALL_PASS")
        """)
        result = subprocess.run([sys.executable, "-c", code], capture_output=True,
                                text=True, timeout=20, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("B1_R25_DOUBLE_INSTALL_PASS", result.stdout)

    @unittest.skipUnless(sys.platform.startswith("linux") and os.geteuid() != 0,
                         "requires non-root Linux and pinned Ronja R25")
    def test_b1_entry_installs_persistent_r25_kernel_policy(self):
        code = textwrap.dedent("""
            import errno
            import socket
            from run_b1_snapshot_observer import require_lifetime_guard
            assert require_lifetime_guard() == "lifetime_guard_loaded_not_host_attestation"
            for family in (socket.AF_INET, socket.AF_INET6):
                try:
                    socket.socket(family, socket.SOCK_STREAM)
                except OSError as exc:
                    assert exc.errno == errno.EPERM, repr(exc)
                else:
                    raise AssertionError("TCP creation survived R25")
            a, b = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                b.sendall(b"x")
                try:
                    a.recvmsg(1)
                except OSError as exc:
                    assert exc.errno == errno.EPERM, repr(exc)
                else:
                    raise AssertionError("recvmsg survived R25")
                a.sendall(b"y")
                assert b.recv(1) == b"y"
            finally:
                a.close()
                b.close()
            print("B1_R25_KERNEL_GUARD_PASS")
        """)
        result = subprocess.run([sys.executable, "-c", code], capture_output=True,
                                text=True, timeout=20, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("B1_R25_KERNEL_GUARD_PASS", result.stdout)


if __name__ == "__main__":
    unittest.main()
