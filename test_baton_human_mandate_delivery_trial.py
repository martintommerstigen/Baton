"""Tests for revocation-after-possible-effect/lost-receipt composition."""
import hashlib
from pathlib import Path
import tempfile
import unittest
from baton_human_mandate_delivery_trial import ApprovalStore, Journal, attempt_send


class HumanMandateDeliveryTrial(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory(prefix="spire-mandate-compose-")
        self.addCleanup(self.t.cleanup)
        self.path = Path(self.t.name) / "journal.sqlite3"
        self.j = Journal(self.path)
        self.approvals = ApprovalStore()
        self.effects = []

    def send(self, target, content):
        self.effects.append((target,content))

    def proof(self, target="vev", content="invitation"):
        return self.approvals.approve(target,content)

    def sha(self, content="invitation"):
        return hashlib.sha256(content.encode()).hexdigest()

    def test_revoke_before_effect_is_canceled_not_attempted(self):
        approval = self.proof()
        self.approvals.revoke()
        self.assertFalse(attempt_send(self.j,self.approvals,"a",approval,
                                      "vev","invitation",self.send))
        self.assertEqual("canceled_before_effect",self.j.get("a")["state"])
        self.assertEqual([],self.effects)

    def test_negative_control_revoke_after_gate_before_external_effect_is_unsafe(self):
        # A deliberate counterexample to this simple two-step model.
        # The trusted external adapter MUST independently enforce a final
        # approval/epoch check at its last cancellable effect boundary.
        # This test PASSES by demonstrating an unsafe fake effect, not safety.
        proof = self.proof()
        def callback_with_revocation(target, content):
            self.approvals.revoke()
            self.send(target,content)
        self.assertTrue(attempt_send(self.j,self.approvals,"a",proof,
                                     "vev","invitation",callback_with_revocation))
        self.assertEqual([("vev","invitation")], self.effects)
        self.assertEqual("click_returned_unconfirmed",self.j.get("a")["state"])
        self.assertFalse(self.approvals.active)

    def test_lost_ack_after_fake_effect_plus_revoke_remains_uncertain(self):
        approval = self.proof()
        def lose_ack(target, content):
            self.send(target,content)
            raise ConnectionError("acknowledgement lost after possible click")
        self.assertTrue(attempt_send(self.j,self.approvals,"a",approval,
                                     "vev","invitation",lose_ack))
        self.approvals.revoke()
        self.assertEqual("delivery_uncertain",self.j.get("a")["state"])
        with self.assertRaises(ValueError):
            self.j.transition("a","canceled_before_effect")
        self.assertEqual([("vev","invitation")],self.effects)

    def test_restart_does_not_blind_resend_even_new_approval(self):
        approval = self.proof()
        attempt_send(self.j,self.approvals,"a",approval,
                     "vev","invitation",lambda *a: (_ for _ in ()).throw(
                         ConnectionError("unconfirmed")))
        self.approvals.revoke()
        # Re-approval in a new generation does not turn the SAME intent into
        # a fresh permission or undo unresolved possible delivery.
        self.approvals.active = True
        renewed = self.proof()
        restarted = Journal(self.path)
        self.assertFalse(attempt_send(restarted,self.approvals,"a",renewed,
                                      "vev","invitation",self.send))
        self.assertEqual([] ,self.effects)
        self.assertEqual("delivery_uncertain",restarted.get("a")["state"])

    def test_wrong_digest_or_target_does_not_get_effect(self):
        approval = self.proof()
        self.assertFalse(attempt_send(self.j,self.approvals,"a",approval,
                                      "som","invitation",self.send))
        self.assertFalse(attempt_send(self.j,self.approvals,"b",approval,
                                      "vev","edited message",self.send))
        self.assertEqual([],self.effects)

    def test_click_return_value_is_not_delivery_proof(self):
        proof = self.proof()
        attempt_send(self.j,self.approvals,"a",proof,
                     "vev","invitation",self.send)
        self.assertEqual("click_returned_unconfirmed",self.j.get("a")["state"])
        self.assertIsNone(self.j.get("a")["receipt"])

    def test_later_source_bound_reply_can_resolve_uncertainty(self):
        proof = self.proof()
        attempt_send(self.j,self.approvals,"a",proof,
                     "vev","invitation",lambda *args: (_ for _ in ()).throw(
                         ConnectionError("ack lost")))
        self.approvals.revoke()
        self.assertTrue(self.j.observe("a",new_message_id="new-user-id",
                                      actual_reply_id="new-assistant-id",
                                      exact_target="vev",exact_digest=self.sha(),
                                      source_bound=True,after_baseline=True))
        self.assertEqual("source_reply_observed",self.j.get("a")["state"])
        self.assertEqual("new-assistant-id",self.j.get("a")["receipt"])

    def test_stale_message_or_wrong_source_cannot_resolve(self):
        proof=self.proof()
        attempt_send(self.j,self.approvals,"a",proof,
                     "vev","invitation",lambda *args: (_ for _ in ()).throw(
                         ConnectionError("ack lost")))
        for source, newer, target in [(False, True,"vev"),(True, False,"vev"),
                                      (True,True,"som")]:
            self.assertFalse(self.j.observe("a",new_message_id="some-id",
                             actual_reply_id="reply-id",exact_target=target,
                             exact_digest=self.sha(),source_bound=source,
                             after_baseline=newer))
        self.assertEqual("delivery_uncertain",self.j.get("a")["state"])

    def test_uncertain_A_does_not_globally_veto_independent_B(self):
        p1=self.proof(target="vev")
        attempt_send(self.j,self.approvals,"a",p1,"vev","invitation",
                     lambda *args: (_ for _ in ()).throw(ConnectionError("unknown")))
        p2=self.proof(target="siv",content="different intent")
        self.assertTrue(attempt_send(self.j,self.approvals,"b",p2,
                                     "siv","different intent",self.send))
        self.assertEqual("delivery_uncertain",self.j.get("a")["state"])
        self.assertEqual("click_returned_unconfirmed",self.j.get("b")["state"])
        self.assertEqual([("siv","different intent")],self.effects)

    def test_canceled_before_effect_must_not_be_forged_as_reply(self):
        p=self.proof()
        self.approvals.revoke()
        attempt_send(self.j,self.approvals,"a",p,"vev","invitation",self.send)
        self.assertFalse(self.j.observe("a",new_message_id="fake",
                            actual_reply_id="fake",exact_target="vev",
                            exact_digest=self.sha(),source_bound=True,
                            after_baseline=True))
        self.assertEqual("canceled_before_effect",self.j.get("a")["state"])


if __name__ == "__main__":
    unittest.main()
