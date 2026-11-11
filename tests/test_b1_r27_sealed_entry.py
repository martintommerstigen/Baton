"""B1 H26 orchestration negatives; no browser, no UI writes or credentials."""
import os
import unittest
from unittest.mock import Mock, patch

from b1_snapshot_relay import SnapshotUncertain
from run_b1_r27_sealed_observer import run_sealed_observation, EXPECTED_SEAL

SOURCE = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
TARGET = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
ARGS = dict(source=SOURCE, source_turn_id="turn-001", target=TARGET,
            message_id="wake-001", payload_sha256="a" * 64,
            snapshot_socket="/safe/collector.sock", broker_socket="/safe/broker.sock",
            collector_uid=29101, broker_uid=29103)


class FakeStream:
    def __init__(self, log):
        self.log = log
        self.closed = False
    def settimeout(self, n):
        self.log.append(("timeout", n))
    def connect(self, endpoint):
        self.log.append(("connect", endpoint))
    def close(self):
        self.closed = True
        self.log.append(("close",))


class FakeSealed:
    receipt = EXPECTED_SEAL
    def snapshot_query(self, request):
        return {"state": "synthetic"}
    def witness_query(self, request):
        return {"state": "synthetic"}


class H26Entry(unittest.TestCase):
    def setUp(self):
        self.log = []
        self.streams = []
        self.patch_uid = patch.multiple(os, geteuid=lambda: 29102,
                                        getuid=lambda: 29102)
        self.patch_uid.start()
        self.addCleanup(self.patch_uid.stop)
        self.pause = Mock(side_effect=lambda: self.log.append(("pause",)) or False)
        self.guard = Mock(side_effect=lambda: self.log.append(("R25",)) or
                          "lifetime_guard_loaded_not_host_attestation")
        self.preflight = Mock(side_effect=lambda: self.log.append(("R24",)) or
                              {"status": "scoped_preflight_pass_not_attestation",
                               "checks": ["distinct_uid", "no_inherited_sockets",
                                          "profile_open_denied",
                                          "declared_loopback_cdp_unreachable",
                                          "snapshot_peer_uid", "tcp_socket_families_denied"]})
        self.endpoint = Mock(side_effect=lambda path, uid:
                             self.log.append(("endpoint", path, uid)))
        self.seal = Mock(side_effect=lambda *a, **kw:
                         self.log.append(("R27",)) or FakeSealed())
        self.observer = Mock(side_effect=lambda **kw:
                             self.log.append(("B1",)) or {"state": "observed_synthetic"})
        def make_stream(*args):
            sock = FakeStream(self.log)
            self.streams.append(sock)
            return sock
        self.patch_socket = patch("run_b1_r27_sealed_observer.socket.socket",
                                  side_effect=make_stream)
        self.patch_socket.start()
        self.addCleanup(self.patch_socket.stop)

    def run_it(self, **overrides):
        kwargs = dict(ARGS, pause_checker=self.pause, preflight=self.preflight,
                      install_guard=self.guard, check_endpoint=self.endpoint,
                      sealer=self.seal, observer=self.observer)
        kwargs.update(overrides)
        return run_sealed_observation(**kwargs)

    def test_order_and_four_separate_sockets(self):
        result = self.run_it()
        self.assertEqual(result["state"], "observed_synthetic")
        self.assertEqual(len(self.streams), 4)
        self.assertTrue(all(s.closed for s in self.streams))
        self.assertLess(self.log.index(("R25",)), self.log.index(("R24",)))
        self.assertLess(self.log.index(("R24",)),
                        self.log.index(("connect", ARGS["snapshot_socket"])))
        self.assertLess(self.log.index(("R27",)), self.log.index(("B1",)))
        self.assertEqual(self.seal.call_args.kwargs["approved_snapshot"]["payload_sha256"],
                         ARGS["payload_sha256"])
        self.assertEqual([x for x in self.log if x[0] == "connect"],
                         [("connect", ARGS["snapshot_socket"])] * 3 +
                         [("connect", ARGS["broker_socket"])])

    def test_pause_blocks_before_kernel_and_network(self):
        self.pause.return_value = True
        self.pause.side_effect = None
        with self.assertRaises(PermissionError):
            self.run_it()
        self.guard.assert_not_called()
        self.assertFalse(self.streams)

    def test_preflight_failure_blocks_preconnection(self):
        self.preflight.side_effect = PermissionError("missing isolation")
        with self.assertRaises(PermissionError):
            self.run_it()
        self.assertFalse(self.streams)
        self.seal.assert_not_called()

    def test_incomplete_preflight_is_rejected(self):
        self.preflight.side_effect = None
        self.preflight.return_value = {
            "status": "scoped_preflight_pass_not_attestation",
            "checks": ["distinct_uid", "no_inherited_sockets",
                       "profile_open_denied", "declared_loopback_cdp_unreachable",
                       "snapshot_peer_uid"]}
        with self.assertRaises(PermissionError):
            self.run_it()
        self.assertFalse(self.streams)

    def test_guard_receipt_forgery_denied(self):
        self.guard.side_effect = None
        self.guard.return_value = "claimed_ok"
        with self.assertRaises(PermissionError):
            self.run_it()
        self.preflight.assert_not_called()
        self.assertFalse(self.streams)

    def test_invalid_source_payload_rejected_before_guard(self):
        with self.assertRaises(ValueError):
            self.run_it(payload_sha256="b" * 63)
        self.guard.assert_not_called()
        self.assertFalse(self.streams)

    def test_r27_seal_failure_closes_all_streams(self):
        self.seal.side_effect = PermissionError("undeclared socket")
        with self.assertRaises(PermissionError):
            self.run_it()
        self.assertEqual(len(self.streams), 4)
        self.assertTrue(all(s.closed for s in self.streams))
        self.observer.assert_not_called()

    def test_invalid_r27_receipt_never_observes(self):
        self.seal.side_effect = None
        self.seal.return_value = Mock(receipt="forged")
        with self.assertRaises(PermissionError):
            self.run_it()
        self.observer.assert_not_called()
        self.assertTrue(all(s.closed for s in self.streams))

    def test_uncertain_witness_propagates_without_retry(self):
        self.observer.side_effect = SnapshotUncertain("possibly committed")
        with self.assertRaises(SnapshotUncertain):
            self.run_it()
        self.observer.assert_called_once()
        self.seal.assert_called_once()
        self.assertTrue(all(s.closed for s in self.streams))

    def test_changed_pause_during_preconnection_denies(self):
        calls = [False] * 6 + [True]
        self.pause.side_effect = lambda: calls.pop(0) if calls else True
        with self.assertRaises(PermissionError):
            self.run_it()
        self.observer.assert_not_called()
        self.assertTrue(all(s.closed for s in self.streams))


if __name__ == "__main__":
    unittest.main()
