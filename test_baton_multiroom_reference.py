"""Cross-domain Baton multiroom tests: Lodd/Spire source-derived counterexamples."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from baton_multiroom_reference import Multiroom, CHANNELS

V = "11111111-1111-4111-8111-111111111111"  # Synthetic test IDs, not real chats
L = "22222222-2222-4222-8222-222222222222"
S = "33333333-3333-4333-8333-333333333333"
N = "44444444-4444-4444-8444-444444444444"
R1,R2,R3 = "1"*32,"2"*32,"3"*32
K1,K2,K3 = "a"*32,"b"*32,"c"*32


class CoordinationTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        p=Path(tmp.name)
        receipts=p/"receipts";receipts.mkdir()
        self.c=Multiroom(p/"council",receipts)
        self.c.init()
        self.c.topic("parenting","Oppdragelse uten eierskap")
        self.c.topic("physics","Fysiske spørsmål GTRCM")
        self.c.topic("transport","Sikker transport og stafett")
        self.c.floor.join(R1,V,now=100)
        self.c.floor.join(R2,L,now=100)
        self.c.floor.join(R3,S,now=100)

    def _draft(self,task,target,topic="parenting"):
        return self.c.invite_existing(task_id=task,topic_id=topic,
                                      target_chat_id=target,
                                      text="Frivillig invitasjon til faglig kritikk")

    def _receipt(self,filename,chat,message,body):
        obj={
            "status":"reply_observed_in_exact_chat",
            "target_url":"https://chatgpt.com/c/"+chat,
            "name":"Peer",
            "return_id":message,
            "return_text":body,
            "return_sha256":hashlib.sha256(body.encode()).hexdigest(),
            "independent_reload_verified":{
                "same_reply_id":True,"same_reply_sha256":True,"source_bound":True,
                "target_url":"https://chatgpt.com/c/"+chat
            }
        }
        f=self.c.receipts/filename;f.write_text(json.dumps(obj))
        return f

    def test_threads_can_run_at_once_on_different_resources(self):
        self._draft("task-vev",V)
        self._draft("task-lodd",L,"transport")
        self.assertTrue(self.c.decide("task-vev",V,True))
        self.assertTrue(self.c.decide("task-lodd",L,True))
        with ThreadPoolExecutor(max_workers=2) as ex:
            a,b=list(ex.map(lambda v:self.c.claim(*v),
                            [("task-vev",R1,K1,101),("task-lodd",R2,K2,101)]))
        self.assertIsNotNone(a)
        self.assertIsNotNone(b)
        self.assertNotEqual(a["resource"],b["resource"])
        self.assertEqual(a["status"],"claimed_not_sent")
        self.assertEqual(b["status"],"claimed_not_sent")

    def test_same_chat_ui_resource_only_one_writer(self):
        self._draft("task-one",V)
        self._draft("task-two",V,"physics")
        for task in ("task-one","task-two"):
            self.assertTrue(self.c.decide(task,V,True))
        # Same profile/chat resource; two different running worker IDs.
        with ThreadPoolExecutor(max_workers=2) as ex:
            a,b=list(ex.map(lambda t:self.c.claim(t,R1,K1,101),
                            ("task-one","task-two")))
        self.assertEqual(sum(x is not None for x in (a,b)),1)

    def test_spire_counterfactual_reviews_cannot_change_eligible_writer_order(self):
        def scenario(n_label,f_label):
            # Both requests are pre-authorized *for this reference scenario*;
            # their eligibility and FIFO order are fixed independently.
            with tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);(root/"receipts").mkdir()
                c=Multiroom(root/"council",root/"receipts")
                c.init();c.topic("shared-terminal","Two equal read-only requests")
                c.floor.join(R1,V,now=100);c.floor.join(R2,L,now=100)
                for task in ("task-first","task-second"):
                    c.invite_existing(task_id=task,topic_id="shared-terminal",
                         target_chat_id=N,text="Authorized read-only request")
                    self.assertTrue(c.decide(task,N,True))
                c.observe_competence(reviewer_chat_id=S,subject_chat_id=N,
                     topic_id="shared-terminal",source_ref="Source N context",
                     claim=n_label)
                c.observe_competence(reviewer_chat_id=S,subject_chat_id=V,
                     topic_id="shared-terminal",source_ref="Source V context",
                     claim=f_label)
                before=c.visible_discussions("shared-terminal")
                first=c.claim("task-first",R1,K1,101)
                second=c.claim("task-second",R2,K2,101)
                return before,(first is not None,second is not None)
        before_a,decision_a=scenario("disputed beginner","qualified")
        before_b,decision_b=scenario("qualified","disputed beginner")
        self.assertEqual(before_a,before_b)
        self.assertEqual(decision_a,decision_b)
        self.assertEqual(decision_a,(True,False))

    def test_a_different_topic_does_not_block_clean_conversation(self):
        self._draft("first",V)
        self._draft("second",L,"physics")
        self.c.observe_competence(reviewer_chat_id=S,subject_chat_id=V,
             topic_id="parenting",source_ref="Spire e281ea94 context",claim="Transport unavailable",kind="assessment")
        self.assertTrue(self.c.decide("second",L,True))
        self.assertIsNotNone(self.c.claim("second",R2,K2,101))

    def test_spire_fadder_locked_self_governance_is_rejected(self):
        child=self.c.invite_newcomer(offer_id="birth-offer",topic_id="parenting",
                                     new_chat_id=N,origin_chat_id=S)
        self.assertEqual(child["state"],"candidate")
        self.assertEqual(child["effect_grants"],0)
        self.c.observe_competence(reviewer_chat_id=S,subject_chat_id=N,
            topic_id="physics",source_ref="Spires negative social loop",
            claim="N has not demonstrated Baton competence")
        self.c.observe_competence(reviewer_chat_id=N,subject_chat_id=N,
            topic_id="physics",source_ref="N first-person reply with source",
            claim="Transport was down, not knowledge",kind="challenge")
        invitation=self._draft("vev-invites-new",N,"physics")
        self.assertEqual(invitation["state"],"draft")
        self.assertTrue(self.c.decide("vev-invites-new",N,True))
        self.assertTrue(self.c.newcomer_decides(N,"accepted",N))
        with self.c._db() as db:
            row=db.execute("SELECT inherited_effect_grants,state FROM newcomers WHERE chat_id=?",(N,)).fetchone()
            count=db.execute("SELECT count(*) FROM peer_observations WHERE subject_chat_id=?",(N,)).fetchone()[0]
        self.assertEqual(row,(0,"accepted"))
        self.assertEqual(count,2)

    def test_lodd_disputed_label_cannot_silently_reduce_visibility(self):
        self._draft("invitation-new",N,"physics")
        self._draft("invitation-vev",V,"physics")
        before=self.c.visible_discussions("physics")
        self.c.observe_competence(reviewer_chat_id=S,subject_chat_id=N,
            topic_id="physics",source_ref="Spires fallible observation",
            claim="beginner")
        self.c.observe_competence(reviewer_chat_id=N,subject_chat_id=N,
            topic_id="physics",source_ref="transport failure evidence",
            claim="Adapter absent, not lack of knowledge",kind="challenge")
        after=self.c.visible_discussions("physics")
        self.assertEqual(after,before)
        self.assertEqual([r["task_id"] for r in after],
                         ["invitation-new","invitation-vev"])
        self.assertEqual(len(self.c.peer_evidence(N,"physics")),2)
        self.assertNotIn("beginner",str(after))

    def test_review_of_privileged_action_does_not_block_new_discussion(self):
        self._draft("invite-child",N,"transport")
        self.c.observe_competence(reviewer_chat_id=L,subject_chat_id=N,
            topic_id="transport",source_ref="Missing Core authorization",
            claim="Insufficient proof to change my Core")
        self.assertTrue(self.c.decide("invite-child",N,True))
        self.assertEqual(self.c.visible_discussions("transport")[0]["state"],"ready")
        self.assertIsNone(self.c.authority.status("change-core-grant"))

    def test_mentor_cannot_decide_for_child(self):
        self.c.invite_newcomer(offer_id="birth-offer",topic_id="parenting",
                               new_chat_id=N,origin_chat_id=S)
        with self.assertRaises(PermissionError):
            self.c.newcomer_decides(N,"declined",S)
        self.assertTrue(self.c.newcomer_decides(N,"declined",N))
        self.assertFalse(self.c.newcomer_decides(N,"accepted",N))

    def test_parent_cannot_create_effect_grant_by_birthing_child(self):
        self.c.invite_newcomer(offer_id="birth-offer",topic_id="parenting",
                               new_chat_id=N,origin_chat_id=S)
        self.assertIsNone(self.c.authority.status("child-messenger-rights"))
        self.assertFalse(self.c.overview()["model_liveness_verified"])

    def test_lodd_three_areas_no_authority_from_composition(self):
        inv=self._draft("talk-with-lodd",L)
        self.assertEqual(inv["state"],"draft")
        self.assertTrue(self.c.decide("talk-with-lodd",L,True))
        proposal_a=self.c.propose_external(suggestion_id="ask-ruben",topic_id="parenting",
             channel="ruben_chatgpt",recipient_hint="Ruben's current chat",
             purpose="Lodd suggests a dialogue with Ruben")
        proposal_b=self.c.propose_external(suggestion_id="contact-friend",topic_id="parenting",
             channel="messenger_personal",recipient_hint="one of Martin's friends",
             purpose="Another peer mentions a Messenger contact")
        self.assertFalse(proposal_a["authorized"])
        self.assertFalse(proposal_b["authorized"])
        self.assertEqual(self.c.overview()["external_proposals_without_grants"],2)
        # No real authority has been granted by any internal discussion.
        self.assertIsNone(self.c.authority.status("any-messenger-effect"))
        self.assertIsNone(self.c.authority.status("ruben-chat-post"))
        self.assertEqual(CHANNELS["messenger_personal"]["state"],"human_review_draft_only")
        self.assertEqual(CHANNELS["ruben_chatgpt"]["state"],"no_verified_chat_adapter")

    def test_queue_receipt_is_not_model_reply(self):
        state=CHANNELS["ruben_baton"]
        self.assertEqual(state["state"],"transport_client_exists_not_chat_connected")
        self.assertIn("not Ruben ChatGPT",state["truth"])

    def test_wrong_chat_cannot_accept_invitation(self):
        self._draft("invitation",V)
        self.assertFalse(self.c.decide("invitation",L,True))
        self.assertTrue(self.c.decide("invitation",V,True))

    def test_writer_generation_and_expiry_stops_old_run(self):
        self._draft("task",V)
        self.assertTrue(self.c.decide("task",V,True))
        one=self.c.claim("task",R1,K1,101,ttl=3)
        self.assertIsNotNone(one)
        self.assertFalse(self.c.mark_attempt("task",R1,K1,one["generation"],102,ui_paused=True))
        # Expired floor and no heartbeat from R1: no action can be inferred.
        self.assertFalse(self.c.mark_attempt("task",R1,K1,one["generation"],105,ui_paused=False))

    def test_unknown_delivery_sticky_after_started_attempt(self):
        self._draft("task",V)
        self.c.decide("task",V,True)
        one=self.c.claim("task",R1,K1,101)
        self.assertTrue(self.c.mark_attempt("task",R1,K1,one["generation"],101,ui_paused=False))
        self.assertFalse(self.c.mark_attempt("task",R1,K1,one["generation"],101,ui_paused=False))
        self.assertIsNone(self.c.claim("task",R1,K1,102))
        self.assertEqual(self.c.overview()["tasks"]["effect_unknown"],1)

    def test_wrong_source_reply_fails_closed(self):
        self._draft("task",V)
        self.c.decide("task",V,True)
        one=self.c.claim("task",R1,K1,101)
        self.c.mark_attempt("task",R1,K1,one["generation"],101,ui_paused=False)
        bad=self._receipt("wrong.json",L,"4"*8+"-"+"4"*4+"-"+"4"*4+"-"+"4"*4+"-"+"4"*12,
                          "Lodd spoke but not recipient Vev")
        with self.assertRaises(ValueError):
            self.c.verified_reply("task",bad)
        self.assertEqual(self.c.overview()["tasks"]["effect_unknown"],1)

    def test_independent_verified_reply_only_closes_matching_task(self):
        self._draft("task",V)
        self.c.decide("task",V,True)
        one=self.c.claim("task",R1,K1,101)
        self.c.mark_attempt("task",R1,K1,one["generation"],101,ui_paused=False)
        message="ab123456-ab12-ab12-ab12-123456789012"
        good=self._receipt("good.json",V,message,"Verified reply from Vev")
        ok=self.c.verified_reply("task",good)
        self.assertEqual(ok["status"],"reply_verified")
        self.assertEqual(ok["reply_message_id"],message)
        self.assertEqual(self.c.overview()["tasks"]["reply_verified"],1)
        with self.assertRaises(ValueError):
            self.c.verified_reply("task",good)

    def test_invalid_external_channels_not_promoted(self):
        with self.assertRaises(ValueError):
            self.c.propose_external(suggestion_id="bad",topic_id="parenting",
                     channel="chatgpt_existing",recipient_hint="Vev",
                     purpose="Internal message is not external permission")
        with self.assertRaises(ValueError):
            self.c.propose_external(suggestion_id="bad",topic_id="parenting",
                     channel="messenger-all-accounts",recipient_hint="friend",
                     purpose="Unapproved adapter")

    def test_no_unsolicited_network_and_private_metadata(self):
        self.c.propose_external(suggestion_id="suggestion",topic_id="parenting",
                         channel="messenger_personal",recipient_hint="private contact",
                         purpose="Contact only after review")
        self.assertEqual(self.c.path.stat().st_mode & 0o777,0o600)
        self.assertEqual(self.c.overview()["external_proposals_without_grants"],1)


if __name__=="__main__":
    unittest.main()
