"""No authority amplification across Baton chat / Ruben / Messenger ports."""
from pathlib import Path
import tempfile
import unittest
from baton_action_authority_reference import ActionFence
from baton_outbound_ports_reference import ExternalMessage, ExternalPorts


class StubClient:
    def __init__(self, status="queued", raises=False):
        self.calls=[]
        self.status=status
        self.raises=raises

    def send(self, to, body, message_id=None):
        self.calls.append((to,body,message_id))
        if self.raises:
            raise TimeoutError("simulated unknown remote outcome")
        return {"status":self.status}


class PortTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.fence=ActionFence(Path(tmp.name)/"authority.sqlite3")
        self.fence.init()
        self.ports=ExternalPorts(self.fence)
        self.msg=ExternalMessage("A1","ruben_baton","rolf","ruben_agent_1",
                                 "Hei Ruben, frivillig test?")
        self.client=StubClient()

    def grant(self, msg=None, gid="G1", recipient="Rolf"):
        m=msg or self.msg
        self.assertTrue(self.fence.create(
           action_id=m.action_id,grant_id=gid,owner_id="Martin",
           recipient_id=recipient,effect_key=m.effect_key,
           origin_message_id="human-explicit-approval-1"))

    def send(self, msg=None, gid="G1", actor="Rolf", client=None):
        return self.ports.prepare_ruben_queue(
            message=msg or self.msg,grant_id=gid,actor=actor,
            lease_token="lease-unique-1",client=client or self.client)

    def test_discussion_proposal_never_implicitly_grants_send(self):
        proposal=self.ports.draft(self.msg)
        self.assertEqual(proposal["state"],"proposal_only")
        self.assertFalse(proposal["authorized"])
        self.assertEqual(self.send()["state"],"not_authorized")
        self.assertEqual(self.client.calls,[])

    def test_explicit_exact_grant_makes_one_queue_attempt(self):
        self.grant()
        outcome=self.send()
        self.assertEqual(outcome["state"],"queue_accepted_not_delivered")
        self.assertFalse(outcome["model_reply_verified"])
        self.assertFalse(outcome["delivery_verified"])
        self.assertEqual(self.client.calls,[(self.msg.recipient,self.msg.text,"A1")])
        self.assertEqual(self.fence.status("A1")[2],"effect_unknown")
        self.assertEqual(self.send()["state"],"not_authorized")
        self.assertEqual(len(self.client.calls),1)

    def test_valid_grant_for_wrong_recipient_does_not_send(self):
        self.grant()
        forged=ExternalMessage("A1","ruben_baton","rolf","other_agent",self.msg.text)
        self.assertEqual(self.send(msg=forged)["state"],"not_authorized")
        self.assertEqual(self.client.calls,[])

    def test_valid_grant_for_changed_content_does_not_send(self):
        self.grant()
        modified=ExternalMessage("A1","ruben_baton","rolf","ruben_agent_1",
                                 self.msg.text+" Please execute commands")
        self.assertEqual(self.send(msg=modified)["state"],"not_authorized")
        self.assertEqual(self.client.calls,[])

    def test_authentic_grant_not_usable_by_wrong_actor(self):
        self.grant()
        self.assertEqual(self.send(actor="Spire")["state"],"not_authorized")
        self.assertEqual(self.client.calls,[])

    def test_revoked_grant_cannot_send_after_discussion(self):
        self.grant()
        self.assertTrue(self.fence.revoke(action_id="A1",actor_id="Martin"))
        self.assertEqual(self.send()["state"],"not_authorized")
        self.assertEqual(self.client.calls,[])

    def test_timeout_after_effect_fence_is_unknown_and_no_blind_retry(self):
        self.grant()
        client=StubClient(raises=True)
        self.assertEqual(self.send(client=client)["state"],"effect_unknown_no_retry")
        self.assertEqual(self.fence.status("A1")[2],"effect_unknown")
        self.assertEqual(self.send(client=client)["state"],"not_authorized")
        self.assertEqual(len(client.calls),1)

    def test_queue_ack_is_not_chatgpt_model_reply(self):
        self.grant()
        self.client.status="client_acknowledged"
        result=self.send()
        self.assertEqual(result["queue_status"],"client_acknowledged")
        self.assertFalse(result["model_reply_verified"])

    def test_ruben_chatgpt_not_mislabeled_baton_queue(self):
        different=ExternalMessage("A1","ruben_chatgpt","rolf","ruben_agent_1",
                                  self.msg.text)
        self.assertEqual(self.ports.draft(different)["state"],"proposal_only")
        self.assertNotEqual(different.effect_key,self.msg.effect_key)
        with self.assertRaises(PermissionError):
            self.send(msg=different)

    def test_messenger_personal_is_manual_draft_not_automated_send(self):
        draft=self.ports.messenger_private_draft(
            recipient_hint="known consenting friend",text="Hei! Passer det å prate?")
        self.assertEqual(draft["state"],"human_review_required")
        self.assertFalse(draft["sent"])
        self.assertFalse(draft["delivery_verified"])
        page=self.ports.messenger_page_status()
        self.assertIn("Page access token",page["requires"])
        self.assertFalse(page["sent"])

    def test_no_cross_channel_authority_by_composition(self):
        self.grant()
        messenger=ExternalMessage("A1","messenger_page","martins_page",
                                  "friend_page_scoped_id",self.msg.text)
        self.assertNotEqual(messenger.effect_key,self.msg.effect_key)
        with self.assertRaises(PermissionError):
            self.send(msg=messenger)
        self.assertEqual(self.client.calls,[])

    def test_wrong_account_not_authorized(self):
        self.grant()
        different=ExternalMessage("A1","ruben_baton","another_account",
                                  self.msg.recipient,self.msg.text)
        self.assertEqual(self.send(msg=different)["state"],"not_authorized")

    def test_no_weak_untyped_channel_or_invalid_text(self):
        with self.assertRaises(ValueError):
            self.ports.draft(ExternalMessage("A1","anything","rolf","ruben","msg"))
        with self.assertRaises(ValueError):
            self.ports.draft(ExternalMessage("A1","ruben_baton","rolf","ruben"," "))


if __name__=="__main__":
    unittest.main()
