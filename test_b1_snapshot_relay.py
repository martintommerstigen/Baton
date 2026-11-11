"""B1 snapshot-only relay: exact-source, mutation, false-positive, restart gates."""
import hashlib
import json
import os
from pathlib import Path
import socket
import tempfile
import threading
import types
import unittest
from unittest.mock import patch

from b1_snapshot_relay import (SnapshotServer, SnapshotUncertain, _secure_new_socket_path,
                               _unique_pairs, make_snapshot, observe_via_snapshots,
                               snapshot_request)

A = "11111111-1111-4111-8111-111111111111"
B = "22222222-2222-4222-8222-222222222222"
D = hashlib.sha256(b"approved").hexdigest()
COMMAND = f"BATON_WAKE {B} m-1 sha256:{D}"
REQ = snapshot_request(A, "turn-A", B, "m-1", D)
EXPECTED = {"state": "source_snapshot_not_authorship", "source_id": A,
            "origin_turn_id": "turn-A", "source_url": f"https://chatgpt.com/c/{A}",
            "source_text_sha256": hashlib.sha256(COMMAND.encode()).hexdigest()}


class FakeReader:
    def __init__(self):
        self.page = types.SimpleNamespace(url=f"https://chatgpt.com/c/{A}")
        self.text = COMMAND
        self.calls = 0
        self.change_on = None
        self.generating = False

    def is_generating(self, source):
        assert source == A
        return self.generating

    def read_assistant_turn(self, source, turn):
        assert source == A and turn == "turn-A"
        self.calls += 1
        if self.change_on is not None and self.calls >= self.change_on:
            return "mutated"
        return self.text


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.reader = FakeReader()
        self.paused = False
        self.calls = []

    def snapshot(self, req):
        self.calls.append("snapshot")
        return dict(EXPECTED)

    def witness(self, req):
        self.calls.append("witness")
        self.assertEqual(req["source_command"], COMMAND)
        self.assertEqual(req["op"], "observe_source")
        return {"state": "source_observation_recorded_not_authorship"}

    def run_observer(self, **overrides):
        args = dict(source=A, source_turn_id="turn-A", target=B, message_id="m-1",
                    payload_sha256=D, snapshot_query=self.snapshot,
                    witness_query=self.witness, pause_checker=lambda: self.paused)
        args.update(overrides)
        return observe_via_snapshots(**args)

    def test_exact_snapshot_has_two_reads_no_mutation(self):
        self.assertEqual(make_snapshot(self.reader, dict(REQ), source_id=A,
                                       allowed_targets=frozenset({B}),
                                       pause_checker=lambda: False), EXPECTED)
        self.assertEqual(self.reader.calls, 2)

    def test_invalid_route_and_schema_fail_closed(self):
        for changes in ({"op": "cdp"}, {"source_id": B}, {"target_id": A},
                        {"payload_sha256": "ABC"}, {"origin_turn_id": ""},
                        {"message_id": "bad space"}, {"extra": "x"}):
            with self.subTest(changes=changes), self.assertRaises((ValueError, PermissionError)):
                make_snapshot(self.reader, {**REQ, **changes}, source_id=A,
                              allowed_targets=frozenset({B}),
                              pause_checker=lambda: False)
        self.assertEqual(self.reader.calls, 0)

    def test_mutation_quoted_command_and_wrong_url_fail(self):
        self.reader.text = "Example: " + COMMAND
        with self.assertRaises(PermissionError):
            make_snapshot(self.reader, REQ, source_id=A, allowed_targets=frozenset({B}), pause_checker=lambda: False)
        self.reader.text = COMMAND
        self.reader.calls = 0
        self.reader.change_on = 2
        with self.assertRaises(PermissionError):
            make_snapshot(self.reader, REQ, source_id=A, allowed_targets=frozenset({B}), pause_checker=lambda: False)
        self.reader.change_on = None
        self.reader.page.url = f"https://chatgpt.com/c/{B}"
        with self.assertRaises((PermissionError, ValueError)):
            make_snapshot(self.reader, REQ, source_id=A, allowed_targets=frozenset({B}), pause_checker=lambda: False)

    def test_route_allowlist_denies_other_target(self):
        C = "33333333-3333-4333-8333-333333333333"
        with self.assertRaises(PermissionError):
            make_snapshot(self.reader, {**REQ, "target_id": C}, source_id=A,
                          allowed_targets=frozenset({B}), pause_checker=lambda: False)
        self.assertEqual(self.reader.calls, 0)

    def test_generation_pause_and_pause_mutation_fail(self):
        self.reader.generating = True
        with self.assertRaises(PermissionError):
            make_snapshot(self.reader, REQ, source_id=A, allowed_targets=frozenset({B}), pause_checker=lambda: False)
        self.reader.generating = False
        with self.assertRaises(PermissionError):
            make_snapshot(self.reader, REQ, source_id=A, allowed_targets=frozenset({B}), pause_checker=lambda: True)
        ticks = [0]
        def change():
            ticks[0] += 1
            return ticks[0] >= 2
        with self.assertRaises(PermissionError):
            make_snapshot(self.reader, REQ, source_id=A, allowed_targets=frozenset({B}), pause_checker=change)

    def test_observer_three_snapshots_one_witness(self):
        self.assertEqual(self.run_observer()["classification"],
                         "snapshot_observation_not_chatgpt_authorship")
        self.assertEqual(self.calls, ["snapshot", "snapshot", "witness", "snapshot"])

    def test_forged_snapshot_is_not_authorship_proof(self):
        # A fake collector can return matching metadata. This is a known
        # false positive until OS isolation and independent UI recheck exist.
        self.assertEqual(self.run_observer()["state"],
                         "source_observation_recorded_not_authorship")

    def test_pre_witness_mismatch_does_not_commit(self):
        def bad(req):
            return {**EXPECTED, "source_text_sha256": "0" * 64}
        with self.assertRaises(PermissionError):
            self.run_observer(snapshot_query=bad)
        self.assertEqual(self.calls, [])

    def test_snapshot_wrong_url_and_extra_field_rejected(self):
        for change in ({"source_url": f"https://example.com/c/{A}"}, {"extra": "x"}):
            with self.subTest(change=change), self.assertRaises((PermissionError, ValueError)):
                self.run_observer(snapshot_query=lambda req: {**EXPECTED, **change})
        self.assertEqual(self.calls, [])

    def test_post_commit_mutation_is_uncertain_not_retry(self):
        count = [0]
        def changing(req):
            count[0] += 1
            return {**EXPECTED, "source_text_sha256": "0" * 64} if count[0] == 3 else dict(EXPECTED)
        with self.assertRaises(SnapshotUncertain):
            self.run_observer(snapshot_query=changing)
        self.assertEqual(self.calls, ["witness"])
        self.assertEqual(count[0], 3)

    def test_lost_witness_ack_is_uncertain(self):
        def lost(req):
            self.calls.append("witness")
            raise TimeoutError("after commit")
        with self.assertRaises(SnapshotUncertain):
            self.run_observer(witness_query=lost)
        self.assertEqual(self.calls, ["snapshot", "snapshot", "witness"])

    def test_rejected_witness_cannot_be_success(self):
        with self.assertRaises(SnapshotUncertain):
            self.run_observer(witness_query=lambda req: {"state": "rejected"})

    def test_pause_after_witness_is_uncertain(self):
        n = [0]
        def pause():
            n[0] += 1
            return n[0] >= 5
        with self.assertRaises(SnapshotUncertain):
            self.run_observer(pause_checker=pause)
        self.assertEqual(self.calls.count("witness"), 1)

    def test_duplicate_json_key_rejected(self):
        with self.assertRaises(ValueError):
            json.loads('{"op":"snapshot","op":"cdp"}', object_pairs_hook=_unique_pairs)

    def test_socket_path_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "relay.sock"
            self.assertEqual(_secure_new_socket_path(p), str(p))
            p.symlink_to(Path(td) / "elsewhere")
            with self.assertRaises(PermissionError):
                _secure_new_socket_path(p)

    def test_server_rejects_root_or_same_uid(self):
        with tempfile.TemporaryDirectory() as td:
            with patch("b1_snapshot_relay.os.geteuid", return_value=0):
                with self.assertRaises(PermissionError):
                    SnapshotServer(str(Path(td)/"s.sock"), reader=self.reader,
                                   source_id=A, allowed_targets=frozenset({B}), observer_uid=1001,
                                   pause_checker=lambda: False)
            with patch("b1_snapshot_relay.os.geteuid", return_value=1001):
                with self.assertRaises(PermissionError):
                    SnapshotServer(str(Path(td)/"s.sock"), reader=self.reader,
                                   source_id=A, allowed_targets=frozenset({B}), observer_uid=1001,
                                   pause_checker=lambda: False)


if __name__ == "__main__":
    unittest.main()
