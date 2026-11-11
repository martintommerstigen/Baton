"""B1 H23: Ronja R24 preflight integration negatives, synthetic source only.

No Greg, browser, UI Send or real remote command. Ronja R24 owns the
isolation implementation; these tests check B1's use of its contract.
"""
import hashlib
import unittest

from b1_snapshot_relay import SnapshotUncertain, observe_via_snapshots
from run_b1_snapshot_observer import enforce_scoped_boundary, guarded_query

A = "11111111-1111-4111-8111-111111111111"
B = "22222222-2222-4222-8222-222222222222"
D = "a" * 64
COMMAND = f"BATON_WAKE {B} m-1 sha256:{D}"
GOOD = {
    "status": "scoped_preflight_pass_not_attestation",
    "checks": [
        "distinct_uid", "different_netns", "no_inherited_sockets",
        "profile_open_denied", "declared_loopback_cdp_unreachable",
        "snapshot_peer_uid",
    ],
}
KWARGS = dict(collector_pid=123, collector_uid=1234, profile="/private/profile",
              snapshot_socket="/private/snapshot.sock", cdp_host="127.0.0.1",
              cdp_port=9222)


def boundary(auditor):
    return enforce_scoped_boundary(**KWARGS, auditor=auditor)


def expected_snapshot():
    return {
        "state": "source_snapshot_not_authorship",
        "source_id": A,
        "origin_turn_id": "turn-A",
        "source_url": "https://chatgpt.com/c/" + A,
        "source_text_sha256": hashlib.sha256(COMMAND.encode()).hexdigest(),
    }


def observe(snapshot_query, witness_query, pause_checker=lambda: False):
    return observe_via_snapshots(
        source=A, source_turn_id="turn-A", target=B, message_id="m-1",
        payload_sha256=D, snapshot_query=snapshot_query,
        witness_query=witness_query, pause_checker=pause_checker)


class R24BoundaryContractTests(unittest.TestCase):
    def test_valid_scoped_result_is_not_promoted_to_attestation(self):
        result = boundary(lambda **kw: dict(GOOD))
        self.assertEqual(result["status"], "scoped_preflight_pass_not_attestation")

    def test_unverified_status_and_empty_result_denied(self):
        for response in ({}, None, {"status": "verified", "checks": GOOD["checks"]}):
            with self.subTest(response=response), self.assertRaises(PermissionError):
                boundary(lambda **kw: response)

    def test_required_checks_cannot_be_omitted(self):
        for item in GOOD["checks"]:
            with self.subTest(item=item), self.assertRaises(PermissionError):
                boundary(lambda **kw: {**GOOD,
                    "checks": [x for x in GOOD["checks"] if x != item]})

    def test_either_documented_network_guard_accepted(self):
        checks = ["tcp_socket_families_denied" if x == "different_netns" else x
                  for x in GOOD["checks"]]
        self.assertEqual(boundary(lambda **kw: {**GOOD, "checks": checks}),
                         {**GOOD, "checks": checks})

    def test_duplicate_or_wrongly_typed_check_denied(self):
        for checks in (GOOD["checks"] + ["distinct_uid"], "distinct_uid",
                       GOOD["checks"] + [None]):
            with self.subTest(checks=checks), self.assertRaises(PermissionError):
                boundary(lambda **kw: {**GOOD, "checks": checks})

    def test_real_pinned_r24_rejects_same_uid_as_collector(self):
        # This imports Ronja's actual pinned implementation in CI, not a mock.
        import os
        from remote_security.observer_boundary import audit_observer_boundary, BoundaryDenied
        with self.assertRaises(BoundaryDenied):
            enforce_scoped_boundary(
                collector_pid=os.getpid(), collector_uid=os.geteuid(),
                profile="/private/profile", snapshot_socket="/private/snapshot.sock",
                cdp_host="127.0.0.1", cdp_port=9222,
                auditor=audit_observer_boundary)

    def test_auditor_exception_propagates_fail_closed(self):
        def unavailable(**kw):
            raise PermissionError("collector namespace not inspectable")
        with self.assertRaisesRegex(PermissionError, "namespace"):
            boundary(unavailable)


class GuardedOperationTests(unittest.TestCase):
    def test_successful_synthetic_observation_guards_every_request(self):
        calls = []
        def preflight():
            calls.append("boundary")
        def snapshot(req):
            calls.append("snapshot")
            return expected_snapshot()
        def witness(req):
            calls.append("witness")
            self.assertEqual(req["op"], "observe_source")
            return {"state": "source_observation_recorded_not_authorship"}
        result = observe(guarded_query(snapshot, preflight, lambda: False),
                         guarded_query(witness, preflight, lambda: False))
        self.assertEqual(result["state"], "source_observation_recorded_not_authorship")
        self.assertEqual(calls, ["boundary", "snapshot", "boundary", "snapshot",
                                 "boundary", "witness", "boundary", "snapshot"])

    def test_no_snapshot_or_witness_after_initial_boundary_denial(self):
        calls = []
        def deny():
            raise PermissionError("no OS boundary")
        def query(req):
            calls.append(req)
            return expected_snapshot()
        with self.assertRaises(PermissionError):
            observe(guarded_query(query, deny, lambda: False),
                    guarded_query(query, deny, lambda: False))
        self.assertEqual(calls, [])

    def test_post_witness_boundary_failure_is_uncertain_without_retry(self):
        calls = []
        counter = [0]
        def preflight():
            counter[0] += 1
            if counter[0] == 4:
                raise PermissionError("boundary disappeared after witness")
        def snapshot(req):
            calls.append("snapshot")
            return expected_snapshot()
        def witness(req):
            calls.append("witness")
            return {"state": "source_observation_recorded_not_authorship"}
        with self.assertRaises(SnapshotUncertain):
            observe(guarded_query(snapshot, preflight, lambda: False),
                    guarded_query(witness, preflight, lambda: False))
        self.assertEqual(calls, ["snapshot", "snapshot", "witness"])

    def test_boundary_failure_before_witness_never_submits_witness(self):
        calls = []
        counter = [0]
        def preflight():
            counter[0] += 1
            if counter[0] == 3:
                raise PermissionError("boundary failed before witness")
        def snapshot(req):
            calls.append("snapshot")
            return expected_snapshot()
        def witness(req):
            calls.append("witness")
            return {"state": "source_observation_recorded_not_authorship"}
        with self.assertRaises(SnapshotUncertain):
            observe(guarded_query(snapshot, preflight, lambda: False),
                    guarded_query(witness, preflight, lambda: False))
        self.assertEqual(calls, ["snapshot", "snapshot"])

    def test_pause_flip_during_preflight_prevents_query(self):
        calls = []
        paused = [False]
        def preflight():
            paused[0] = True
        def query(req):
            calls.append(req)
        guarded = guarded_query(query, preflight, lambda: paused[0])
        with self.assertRaises(PermissionError):
            guarded({"op": "snapshot"})
        self.assertEqual(calls, [])

    def test_missing_callbacks_fail_closed(self):
        with self.assertRaises(TypeError):
            guarded_query(None, lambda: None, lambda: False)


if __name__ == "__main__":
    unittest.main()
