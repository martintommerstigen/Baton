"""Pinned B1 H21 -> actual Ronja R22 witness -> B1 SQLite contract.

This uses synthetic DOM/UIDs and no UI Send. It is NOT Greg or ChatGPT live.
"""
from contextlib import closing
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from wake_admission_broker import AdmissionStore
from observe_verified_broker_source import observe_once
from remote_security.observed_source_handoff import ObservedSourceHandoff

A = "11111111-1111-4111-8111-111111111111"
B = "22222222-2222-4222-8222-222222222222"
D = "a" * 64
CMD = f"BATON_WAKE {B} m-1 sha256:{D}"


class Source:
    def __init__(self):
        class Page:
            url = f"https://chatgpt.com/c/{A}"
        self.page = Page()
    def is_generating(self, _):
        return False
    def read_assistant_turn(self, _, __):
        return CMD


class ActualR22Contract(unittest.TestCase):
    def test_source_observe_controller_spend_begin_click_and_restart(self):
        with tempfile.TemporaryDirectory() as td:
            db = str(Path(td) / "broker.sqlite")
            pause = str(Path(td) / "PAUSE_UI_WRITES")
            inner = AdmissionStore(db, pause, {B})
            broker_uid = os.geteuid()
            self.assertGreater(broker_uid, 0)
            observer_uid, controller_uid = broker_uid + 50000, broker_uid + 50001
            handoff = ObservedSourceHandoff(
                inner, broker_uid=broker_uid, observer_uid=observer_uid,
                controller_uid=controller_uid, source_routes={A: {B}})
            def request_as(uid, req):
                with patch("remote_security.observed_source_handoff.kernel_uid",
                           return_value=uid):
                    return handoff.request_from_socket(object(), req)

            observed = observe_once(Source(), A, "turn-A", B, "m-1", D,
                                    lambda req: request_as(observer_uid, req),
                                    lambda: False)
            self.assertEqual(observed["state"],
                             "source_observation_recorded_not_authorship")
            envelope = {"sender_id": A, "origin_turn_id": "turn-A",
                        "conversation_id": B, "message_id": "m-1",
                        "payload_sha256": D}
            self.assertEqual(request_as(observer_uid, {"op": "admit", **envelope})["state"],
                             "rejected")
            self.assertEqual(request_as(controller_uid, {"op": "admit", **envelope}),
                             {"state": "admitted_not_delivered"})
            self.assertEqual(request_as(controller_uid, {"op": "begin_click", **envelope}),
                             {"state": "click_started_uncertain"})
            with closing(inner.connect()) as con:
                self.assertEqual(con.execute(
                    "SELECT state FROM admissions WHERE conversation_id=?", (B,)).fetchone(),
                    ("uncertain",))
                self.assertEqual(con.execute(
                    "SELECT state FROM b5_source_witness_v1 WHERE sender_id=?", (A,)).fetchone(),
                    ("spent",))
            # Restart creates a fresh wrapper around the same persisted database.
            reopened = AdmissionStore(db, pause, {B})
            again = ObservedSourceHandoff(
                reopened, broker_uid=broker_uid, observer_uid=observer_uid,
                controller_uid=controller_uid, source_routes={A: {B}})
            with patch("remote_security.observed_source_handoff.kernel_uid",
                       return_value=controller_uid):
                self.assertEqual(again.request_from_socket(
                    object(), {"op": "admit", **envelope})["state"], "rejected")
            with patch("remote_security.observed_source_handoff.kernel_uid",
                       return_value=observer_uid):
                self.assertEqual(again.request_from_socket(
                    object(), {"op": "observe_source", **envelope,
                               "source_command": CMD})["state"], "rejected")

    def test_pause_blocks_controller_admission_even_after_observation(self):
        with tempfile.TemporaryDirectory() as td:
            db = str(Path(td) / "broker.sqlite")
            pause = Path(td) / "PAUSE_UI_WRITES"
            inner = AdmissionStore(db, str(pause), {B})
            broker_uid = os.geteuid()
            observer_uid, controller_uid = broker_uid + 50000, broker_uid + 50001
            handoff = ObservedSourceHandoff(
                inner, broker_uid=broker_uid, observer_uid=observer_uid,
                controller_uid=controller_uid, source_routes={A: {B}})
            with patch("remote_security.observed_source_handoff.kernel_uid",
                       return_value=observer_uid):
                observe_once(Source(), A, "turn-A", B, "m-1", D,
                             lambda req: handoff.request_from_socket(object(), req),
                             lambda: False)
            pause.touch()
            envelope = {"sender_id": A, "origin_turn_id": "turn-A",
                        "conversation_id": B, "message_id": "m-1",
                        "payload_sha256": D}
            with patch("remote_security.observed_source_handoff.kernel_uid",
                       return_value=controller_uid):
                self.assertEqual(handoff.request_from_socket(
                    object(), {"op": "admit", **envelope}),
                    {"state": "rejected", "reason": "paused_or_untrusted"})
            with closing(inner.connect()) as con:
                self.assertEqual(con.execute(
                    "SELECT state FROM b5_source_witness_v1").fetchone(), ("spent",))
                self.assertEqual(con.execute("SELECT COUNT(*) FROM admissions").fetchone(), (0,))


if __name__ == "__main__":
    unittest.main()
