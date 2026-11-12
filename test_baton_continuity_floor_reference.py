"""Deterministic concurrency and no-false-liveness checks, no actual UI writes."""
from concurrent.futures import ThreadPoolExecutor
import sqlite3
import tempfile
from pathlib import Path
import unittest

from baton_continuity_floor_reference import Floor

A="a"*32
B="b"*32
C="c"*32
T1="d"*32
T2="e"*32
CHAT_A="6aef3ac4-86bc-83ed-a4df-89e947bc5a34"
CHAT_B="6aef341a-d850-83ed-a3b2-c735a215bce3"
CHAT_C="6aee69e6-21ec-83eb-8b0e-ab43497695b0"


class FloorTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.db=Path(temp.name)/"floor.sqlite3"
        self.f=Floor(self.db,heartbeat_ttl=10)
        self.f.init()

    def joined(self,now=100):
        self.f.join(A,CHAT_A,now)
        self.f.join(B,CHAT_B,now)

    def test_no_false_liveness_when_empty(self):
        s=self.f.status(100)
        self.assertFalse(s["floor_observed"])
        self.assertFalse(s["guaranteed_model_generation"])

    def test_only_one_stale_run_cannot_represent_continuity(self):
        self.f.join(A,CHAT_A,100)
        self.assertTrue(self.f.status(101)["floor_observed"])
        self.assertFalse(self.f.status(111)["floor_observed"])
        self.assertFalse(self.f.heartbeat(A,111))
        self.assertFalse(self.f.status(111)["floor_observed"])

    def test_register_existing_run_id_again_rejected(self):
        self.f.join(A,CHAT_A,100)
        with self.assertRaises(sqlite3.IntegrityError): self.f.join(A,CHAT_A,101)

    def test_overlap_required_before_offer(self):
        self.f.join(A,CHAT_A,100)
        self.assertFalse(self.f.offer("handoff-1",A,B,101))
        self.f.join(B,CHAT_B,102)
        self.assertTrue(self.f.offer("handoff-1",A,B,103))

    def test_two_phase_ack_and_release(self):
        self.joined()
        self.assertTrue(self.f.offer("handoff-1",A,B,102))
        self.assertFalse(self.f.release(A,"handoff-1",103))
        self.assertTrue(self.f.accept("handoff-1",B,103))
        self.assertTrue(self.f.release(A,"handoff-1",104))
        self.assertEqual([x['run_id'] for x in self.f.status(104)['active_attested_runners']],[B])
        self.assertIn("released",[r[1] for r in self.f.history()])

    def test_recipient_cannot_fake_acceptance_with_wrong_run(self):
        self.joined()
        self.assertTrue(self.f.offer("handoff-1",A,B,102))
        self.f.join(C,CHAT_C,102)
        self.assertFalse(self.f.accept("handoff-1",C,103))
        self.assertFalse(self.f.release(A,"handoff-1",103))

    def test_new_heartbeat_after_accept_but_before_release(self):
        self.joined()
        self.f.offer("handoff-1",A,B,101)
        self.f.accept("handoff-1",B,102)
        self.assertTrue(self.f.heartbeat(A,108))
        self.assertTrue(self.f.heartbeat(B,109))
        self.assertTrue(self.f.release(A,"handoff-1",110))
        self.assertTrue(self.f.status(110)["floor_observed"])

    def test_expired_receiver_blocks_release(self):
        self.joined()
        self.f.offer("handoff-1",A,B,101)
        self.f.accept("handoff-1",B,102)
        self.f.heartbeat(A,110)
        self.assertFalse(self.f.release(A,"handoff-1",111))
        self.assertTrue(self.f.status(111)["floor_observed"])

    def test_active_session_cannot_release_without_handoff(self):
        self.f.join(A,CHAT_A,100)
        self.assertFalse(self.f.release(A,"missing-1",101))

    def test_two_active_different_write_resources(self):
        self.joined()
        ga=self.f.acquire_writer("greg:profile-a",A,T1,101)
        gb=self.f.acquire_writer("greg:profile-b",B,T2,101)
        self.assertEqual(ga,1);self.assertEqual(gb,1)
        self.assertTrue(self.f.writer_valid("greg:profile-a",A,T1,ga,102))
        self.assertTrue(self.f.writer_valid("greg:profile-b",B,T2,gb,102))

    def test_competing_same_resource_only_one_wins(self):
        self.joined()
        with ThreadPoolExecutor(max_workers=2) as pool:
            fa=pool.submit(self.f.acquire_writer,"greg:profile",A,T1,102)
            fb=pool.submit(self.f.acquire_writer,"greg:profile",B,T2,102)
            results=[fa.result(),fb.result()]
        self.assertEqual(sorted(x is not None for x in results),[False,True])

    def test_old_token_cannot_write_after_release_and_reclaim(self):
        self.joined()
        old=self.f.acquire_writer("greg:profile",A,T1,101)
        self.assertTrue(self.f.writer_release("greg:profile",A,T1,old,102))
        fresh=self.f.acquire_writer("greg:profile",B,T2,103)
        self.assertEqual(fresh,old+1)
        self.assertFalse(self.f.writer_valid("greg:profile",A,T1,old,103))
        self.assertTrue(self.f.writer_valid("greg:profile",B,T2,fresh,103))

    def test_expired_lease_reclaim_stale_generation_denied(self):
        self.joined()
        old=self.f.acquire_writer("greg:profile",A,T1,101,ttl=3)
        new=self.f.acquire_writer("greg:profile",B,T2,104)
        self.assertEqual(new,old+1)
        self.assertFalse(self.f.writer_valid("greg:profile",A,T1,old,104))
        self.assertTrue(self.f.writer_valid("greg:profile",B,T2,new,104))

    def test_no_double_release_or_replay(self):
        self.joined()
        gen=self.f.acquire_writer("greg:profile",A,T1,101)
        self.assertFalse(self.f.writer_release("greg:profile",B,T1,gen,102))
        self.assertTrue(self.f.writer_release("greg:profile",A,T1,gen,102))
        self.assertFalse(self.f.writer_release("greg:profile",A,T1,gen,103))

    def test_source_must_release_write_turn_before_handoff(self):
        self.joined()
        gen=self.f.acquire_writer("greg:profile",A,T1,101)
        self.f.offer("handoff-1",A,B,102)
        self.f.accept("handoff-1",B,103)
        self.assertFalse(self.f.release(A,"handoff-1",103))
        self.assertTrue(self.f.writer_release("greg:profile",A,T1,gen,104))
        self.assertTrue(self.f.release(A,"handoff-1",105))

    def test_writer_needs_active_attestation(self):
        self.f.join(A,CHAT_A,100)
        self.assertIsNone(self.f.acquire_writer("greg:profile",A,T1,111))
        self.assertIsNone(self.f.acquire_writer("greg:profile",B,T2,105))

    def test_stale_cannot_exit_claiming_accepted_transfer(self):
        self.joined()
        self.f.offer("handoff-1",A,B,101)
        self.f.accept("handoff-1",B,102)
        self.assertFalse(self.f.release(A,"handoff-1",111))
        self.assertFalse(self.f.status(112)["floor_observed"])

    def test_revived_source_cannot_claim_new_liveness(self):
        self.joined()
        self.f.offer("handoff-1",A,B,101)
        self.f.accept("handoff-1",B,102)
        self.f.release(A,"handoff-1",103)
        self.assertFalse(self.f.heartbeat(A,104))
        self.assertIsNone(self.f.acquire_writer("greg:profile",A,T1,104))

    def test_chats_not_distinct_same_chat_can_run_overlapping(self):
        # Multiple distinct runs may be associated with one chat.
        self.f.join(A,CHAT_A,100)
        self.f.join(B,CHAT_A,101)
        self.assertEqual(len(self.f.status(102)["active_attested_runners"]),2)

    def test_heartbeat_future_or_backward_rejected(self):
        self.f.join(A,CHAT_A,100)
        self.assertFalse(self.f.heartbeat(A,99))
        self.assertFalse(self.f.writer_valid("greg:profile",A,T1,1,99))

    def test_no_undeclared_custom_resource_grant(self):
        self.joined()
        with self.assertRaises(ValueError):
            self.f.acquire_writer("../../etc",A,T1,101)
        with self.assertRaises(ValueError):
            self.f.offer("bad id; command",A,B,102)


if __name__=="__main__":
    unittest.main()
