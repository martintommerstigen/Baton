"""Negative concurrency controls for the cross-chat action/grant fence.

Runs against a temporary SQLite database only. In particular, no ChatGPT
messages, shell commands, real file mutations or external effects are sent.
"""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import unittest

from baton_action_authority_reference import ActionFence


class ActionAuthorityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / "authority.sqlite"
        self.store = ActionFence(self.db)
        self.store.init()

    def create(self, action="A1", grant="G7", owner="Lodd",
               recipient="Spire", effect="vev-research",
               origin="M1"):
        return self.store.create(action_id=action, grant_id=grant,
                  owner_id=owner, recipient_id=recipient,
                  effect_key=effect, origin_message_id=origin)

    def reserve(self, *, action_id, grant_id, lease_token):
        # Older tests exercise an authorized matching actor/operation by default.
        effect = ("archive-source" if (action_id,grant_id) == ("A2","G9")
                  else "vev-research")
        return self.store.reserve(action_id=action_id,grant_id=grant_id,
                   lease_token=lease_token,actor_id="Spire",
                   requested_effect_key=effect)

    def begin_effect(self, *, action_id, grant_id,
                     reserved_revision, lease_token):
        return self.store.begin_effect(action_id=action_id,grant_id=grant_id,
                   reserved_revision=reserved_revision,lease_token=lease_token,
                   actor_id="Spire",requested_effect_key="vev-research")

    def test_valid_baseline_requires_last_fence(self):
        self.assertTrue(self.create())
        self.assertTrue(self.reserve(action_id="A1",grant_id="G7",
                                           lease_token="W1lease"))
        self.assertTrue(self.begin_effect(action_id="A1",grant_id="G7",
                    reserved_revision=1,lease_token="W1lease"))
        self.assertEqual(self.store.status("A1")[2], "effect_unknown")
        self.assertFalse(self.begin_effect(action_id="A1",grant_id="G7",
                         reserved_revision=1,lease_token="W1lease"))

    def test_two_workers_one_reservation(self):
        self.assertTrue(self.create())
        barrier = threading.Barrier(3)
        def worker(token):
            barrier.wait()
            return self.reserve(action_id="A1",grant_id="G7",
                                      lease_token=token)
        with ThreadPoolExecutor(max_workers=2) as pool:
            a = pool.submit(worker, "W1")
            b = pool.submit(worker, "W2")
            barrier.wait()
            results = [a.result(), b.result()]
        self.assertEqual(results.count(True), 1)
        self.assertEqual(results.count(False), 1)

    def test_reserved_rev7_revoked_rev8_stale_lease_is_denied(self):
        self.create()
        self.assertTrue(self.reserve(action_id="A1",
                         grant_id="G7", lease_token="W1lease"))
        self.assertTrue(self.store.revoke(action_id="A1",actor_id="Lodd"))
        self.assertEqual(self.store.status("A1")[1:3], (2, "revoked"))
        self.assertFalse(self.begin_effect(action_id="A1",
                         grant_id="G7",reserved_revision=1,lease_token="W1lease"))
        self.assertTrue(self.store.tombstoned("G7"))

    def test_replay_new_message_id_cannot_resurrect_action(self):
        self.create()
        self.reserve(action_id="A1",grant_id="G7",lease_token="W1lease")
        self.store.revoke(action_id="A1",actor_id="Lodd")
        self.assertFalse(self.create(action="A1",grant="G7",origin="M3"))
        self.assertFalse(self.create(action="A1prime",grant="G7",origin="M3"))
        self.assertTrue(self.store.tombstoned("G7"))

    def test_tombstone_survives_restart(self):
        self.create()
        self.store.revoke(action_id="A1",actor_id="Lodd")
        second = ActionFence(self.db)
        second.init()
        self.assertTrue(second.tombstoned("G7"))
        self.assertFalse(second.create(action_id="A1prime",grant_id="G7",
                          owner_id="Lodd",recipient_id="Spire",
                          effect_key="vev-research",origin_message_id="M3"))

    def test_genuinely_new_authorized_grant_not_globally_banned(self):
        self.create()
        self.store.revoke(action_id="A1",actor_id="Lodd")
        self.assertTrue(self.create(action="A2",grant="G8",
                        origin="M4",effect="vev-research"))
        self.assertTrue(self.reserve(action_id="A2",
                        grant_id="G8",lease_token="W2lease"))
        self.assertFalse(self.store.tombstoned("G8"))

    def test_challenge_only_pauses_its_own_action(self):
        self.create()
        self.create(action="A2",grant="G9",effect="archive-source",origin="M5")
        self.reserve(action_id="A1",grant_id="G7",lease_token="W1lease")
        self.assertTrue(self.store.challenge(action_id="A1",
                    challenge_id="C1",challenger_id="Spire",note="possible wrong target"))
        self.assertEqual(self.store.status("A1")[2],"challenged")
        self.assertFalse(self.store.tombstoned("G7"))
        self.assertFalse(self.begin_effect(action_id="A1",grant_id="G7",
                         reserved_revision=1,lease_token="W1lease"))
        self.assertTrue(self.reserve(action_id="A2",
                        grant_id="G9",lease_token="archivelease"))
        self.assertTrue(self.store.dismiss_challenge(action_id="A1",
                                                    actor_id="Lodd"))
        self.assertTrue(self.reserve(action_id="A1",
                        grant_id="G7",lease_token="newlease"))
        self.assertFalse(self.begin_effect(action_id="A1",
                         grant_id="G7",reserved_revision=1,
                         lease_token="W1lease"))

    def test_challenge_is_not_revocation_or_ownership(self):
        self.create()
        self.store.challenge(action_id="A1",challenge_id="C1",
                             challenger_id="Spire",note="uncertain")
        with self.assertRaises(PermissionError):
            self.store.dismiss_challenge(action_id="A1",actor_id="Vev")
        with self.assertRaises(PermissionError):
            self.store.revoke(action_id="A1",actor_id="Vev")
        self.assertFalse(self.store.tombstoned("G7"))
        self.assertEqual(self.store.status("A1")[2],"challenged")

    def test_revocation_after_commit_must_not_claim_effect_absent(self):
        self.create()
        self.reserve(action_id="A1",grant_id="G7",lease_token="W1lease")
        self.assertTrue(self.begin_effect(action_id="A1",
                grant_id="G7",reserved_revision=1,lease_token="W1lease"))
        self.assertTrue(self.store.revoke(action_id="A1",actor_id="Lodd"))
        self.assertEqual(self.store.status("A1")[2],"effect_unknown")
        self.assertTrue(self.store.tombstoned("G7"))
        self.assertFalse(self.begin_effect(action_id="A1",
                         grant_id="G7",reserved_revision=1,
                         lease_token="W1lease"))

    def test_concurrent_challenge_and_reserve_cannot_start_effect(self):
        self.create()
        barrier=threading.Barrier(3)
        def reserve():
            barrier.wait()
            return self.reserve(action_id="A1",
                           grant_id="G7",lease_token="W1lease")
        def challenge():
            barrier.wait()
            return self.store.challenge(action_id="A1",
                       challenge_id="C1",challenger_id="Vev",
                       note="scope must be reconsidered")
        with ThreadPoolExecutor(max_workers=2) as pool:
            a=pool.submit(reserve);b=pool.submit(challenge)
            barrier.wait()
            a.result();self.assertTrue(b.result())
        self.assertEqual(self.store.status("A1")[2],"challenged")
        self.assertFalse(self.begin_effect(action_id="A1",
                         grant_id="G7",reserved_revision=1,
                         lease_token="W1lease"))

    def test_reusing_existing_grant_for_new_action_also_denied(self):
        self.create()
        self.assertFalse(self.create(action="A2",grant="G7",origin="newMsg"))
        self.assertEqual(self.store.status("A1")[2],"pending")

    def test_invalid_identifiers_rejected(self):
        with self.assertRaises(ValueError):
            self.create(action="../A1")
        with self.assertRaises(ValueError):
            self.create(action="A1",grant="G7",origin="M with spaces")
        with self.assertRaises(ValueError):
            self.reserve(action_id="A1",grant_id="G7",lease_token="")
        with self.assertRaises(ValueError):
            self.begin_effect(action_id="A1",grant_id="G7",
                          reserved_revision=-1,lease_token="W1")

    def test_no_automatic_recreation_after_later_challenge(self):
        self.create()
        self.store.challenge(action_id="A1",challenge_id="C1",
                             challenger_id="Siv",note="new context")
        self.store.revoke(action_id="A1",actor_id="Lodd")
        self.assertFalse(self.create(action="A1new",grant="G7",
                         origin="Mnew"))
        self.assertEqual(self.store.status("A1")[2],"revoked")


    def test_authentic_grant_cannot_be_used_by_wrong_actor(self):
        self.create(recipient="Vev")
        # K3 has the real unrevoked G7, but is not its recipient.
        self.assertFalse(self.store.reserve(action_id="A1",grant_id="G7",
                         lease_token="stolen",actor_id="K3",
                         requested_effect_key="vev-research"))
        self.assertEqual(self.store.status("A1")[2],"pending")
        self.assertTrue(self.store.reserve(action_id="A1",grant_id="G7",
                        lease_token="vev-lease",actor_id="Vev",
                        requested_effect_key="vev-research"))
        self.assertFalse(self.store.begin_effect(action_id="A1",
                         grant_id="G7",reserved_revision=1,
                         lease_token="vev-lease",actor_id="K3",
                         requested_effect_key="vev-research"))
        self.assertTrue(self.store.begin_effect(action_id="A1",
                        grant_id="G7",reserved_revision=1,
                        lease_token="vev-lease",actor_id="Vev",
                        requested_effect_key="vev-research"))

    def test_authentic_grant_wrong_operation_is_rejected(self):
        self.create(recipient="Vev",effect="read-only-audit")
        self.assertFalse(self.store.reserve(action_id="A1",grant_id="G7",
                         lease_token="bad-op",actor_id="Vev",
                         requested_effect_key="delete-files"))
        self.assertTrue(self.store.reserve(action_id="A1",grant_id="G7",
                        lease_token="good-op",actor_id="Vev",
                        requested_effect_key="read-only-audit"))
        self.assertFalse(self.store.begin_effect(action_id="A1",
                         grant_id="G7",reserved_revision=1,
                         lease_token="good-op",actor_id="Vev",
                         requested_effect_key="delete-files"))
        self.assertTrue(self.store.begin_effect(action_id="A1",
                        grant_id="G7",reserved_revision=1,
                        lease_token="good-op",actor_id="Vev",
                        requested_effect_key="read-only-audit"))

    def test_wrong_presenter_cannot_change_vev_right_to_receive(self):
        self.create(recipient="Vev")
        self.assertFalse(self.store.reserve(action_id="A1",grant_id="G7",
                         lease_token="K3",actor_id="K3",
                         requested_effect_key="vev-research"))
        self.assertFalse(self.store.tombstoned("G7"))
        self.assertTrue(self.store.reserve(action_id="A1",grant_id="G7",
                        lease_token="Vev",actor_id="Vev",
                        requested_effect_key="vev-research"))
        # Challenge is a distinct relation, NOT delegated action authority.
        self.assertTrue(self.store.challenge(action_id="A1",
                        challenge_id="C2",challenger_id="K3",
                        note="the context is unclear"))
        self.assertFalse(self.store.begin_effect(action_id="A1",
                         grant_id="G7",reserved_revision=1,
                         lease_token="Vev",actor_id="Vev",
                         requested_effect_key="vev-research"))
        self.assertTrue(self.store.dismiss_challenge(action_id="A1",
                        actor_id="Lodd"))
        self.assertTrue(self.store.reserve(action_id="A1",grant_id="G7",
                        lease_token="newVev",actor_id="Vev",
                        requested_effect_key="vev-research"))



if __name__ == "__main__":
    unittest.main()
