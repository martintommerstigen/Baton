"""Self-service Baton onboarding: no fake tool access and no UI side effect."""
import inspect
import unittest

from baton_agent_onboarding import (
    agent_bootstrap_appendix, contact_state, contact_guide_text,
    inbound_relay_envelope
)
from baton_model_bridge import bootstrap_message, attach_model_bridge
from baton_model_protocol import parse_assistant_tool_call

CHAT="6aef00a2-02d0-83ed-84a9-b2648808819a"
NONCE="a"*32
REQ="b"*32


class AgentOnboardingTests(unittest.TestCase):
    def test_no_chat_to_choose(self):
        state=contact_state(None)
        self.assertEqual(state["state"],"choose_conversation")
        self.assertFalse(state["can_initiate_peer_message"])

    def test_varde_inbound_only_is_not_outbound_authority(self):
        state=contact_state(CHAT,inbound_only=True)
        self.assertEqual(state["state"],"inbound_only")
        self.assertFalse(state["current_access_proven"])
        self.assertFalse(state["can_initiate_peer_message"])
        self.assertIn("mottatt invitasjon",state["next_step"])

    def test_ordinary_chat_no_model_bridge(self):
        state=contact_state(CHAT)
        self.assertEqual(state["state"],"bridge_inactive")
        self.assertFalse(state["can_initiate_peer_message"])
        self.assertIn("Aktiver Baton",state["next_step"])

    def test_bootstrap_sent_is_not_capability_proof(self):
        state=contact_state(CHAT,bridge_active=True,probe_verified=False)
        self.assertEqual(state["state"],"bridge_probe_unconfirmed")
        self.assertFalse(state["can_initiate_peer_message"])
        self.assertFalse(state["current_access_proven"])

    def test_actual_nonce_bound_probe_allows_attempt_not_delivery_claim(self):
        state=contact_state(CHAT,bridge_active=True,probe_verified=True)
        self.assertEqual(state["state"],"ready_to_attempt")
        self.assertTrue(state["can_initiate_peer_message"])
        self.assertTrue(state["current_access_proven"])
        self.assertIn("ikke levert",state["next_step"])

    def test_pause_blocks_even_verified_bridge(self):
        state=contact_state(CHAT,bridge_active=True,probe_verified=True,pause=True)
        self.assertEqual(state["state"],"ui_paused")
        self.assertFalse(state["can_initiate_peer_message"])
        self.assertIn("PAUSE_UI_WRITES",state["next_step"])

    def test_uncertain_receipt_blocks_blind_retry_even_with_bridge(self):
        state=contact_state(CHAT,bridge_active=True,probe_verified=True,uncertain=True)
        self.assertEqual(state["state"],"uncertain")
        self.assertFalse(state["can_initiate_peer_message"])
        self.assertIn("request_id",state["next_step"])

    def test_invalid_assumed_probe_rejected(self):
        with self.assertRaises(ValueError):
            contact_state(CHAT,probe_verified=True)
        with self.assertRaises(ValueError):
            contact_state(CHAT,bridge_active="True")

    def test_only_exact_uuid_chat_addresses(self):
        for invalid in ("", "not-a-chat","../x","6aef00a2-02d0-83ed-84a9-b2648808819a?q=1",
                        "6aef00a2-02d0-83ed-84a9-b2648808819a\nBATON_CHAT_V1",
                        "https://chatgpt.com/c/"+CHAT):
            with self.assertRaises(ValueError):
                contact_state(invalid)

    def test_guide_is_actionable_but_not_executable(self):
        guide=contact_guide_text(CHAT,inbound_only=True)
        self.assertIn("BATON_CHAT_V1",guide)
        self.assertIn("DC",guide)
        self.assertIn("ikke identitetsbevis",guide)
        self.assertIn("inbound_only",guide)
        self.assertIn("plassholderne er aldri kjørbare",guide)
        self.assertIsNone(parse_assistant_tool_call(guide,NONCE))

    def test_guide_in_paused_mode_does_not_invite_send(self):
        guide=contact_guide_text(CHAT,bridge_active=True,probe_verified=True,pause=True)
        self.assertIn("PAUSE_UI_WRITES",guide)
        self.assertIn("ui_paused",guide)
        self.assertIsNone(parse_assistant_tool_call(guide,NONCE))

    def test_appended_bootstrap_is_for_active_tool_context(self):
        addendum=agent_bootstrap_appendix()
        self.assertIn("INITIATE",addendum)
        self.assertIn("BATON_CHAT_V1",addendum)
        self.assertIn("NEW request_id",addendum)
        self.assertIn("not only",addendum)
        self.assertIn("not proof",addendum)

    def test_bootstrap_still_exactly_one_nonce_bound_hostname_probe(self):
        text=bootstrap_message(NONCE,"/home/olliver",request_id=REQ)
        self.assertIn("BATON PEER QUICKSTART",text)
        self.assertLess(len(text),4000)
        lines=[line for line in text.splitlines() if line.startswith("BATON_TOOL_V2 ")]
        self.assertEqual(len(lines),1)
        req=parse_assistant_tool_call(lines[0],NONCE)
        self.assertEqual(req["request_id"],REQ)
        self.assertEqual(req["argv"],["/usr/bin/hostname"])
        self.assertEqual(req["cwd"],"/home/olliver")

    def test_bootstrap_rejects_untrusted_request_id(self):
        with self.assertRaises(ValueError):
            bootstrap_message(NONCE,"/home/olliver",request_id="bad")

    def test_quickstart_button_is_read_only(self):
        source=inspect.getsource(attach_model_bridge)
        def_body=source.split("    def show_peer_guide():",1)[1].split("    peer_guide.clicked",1)[0]
        self.assertIn("contact_guide_text(",def_body)
        self.assertIn("QMessageBox.information",def_body)
        self.assertNotIn("transmit(",def_body)
        self.assertNotIn("start_chat_relay(",def_body)
        self.assertNotIn("execute_on_greg(",def_body)
        self.assertIn('peer_guide.clicked.connect(show_peer_guide)',source)

    def test_ready_requires_probe_bound_to_current_session(self):
        source=inspect.getsource(attach_model_bridge)
        self.assertIn('probe_request_id',source)
        self.assertIn('request_id==current.get("probe_request_id")',source)
        self.assertIn('outcome.get("exit_code")==0',source)
        self.assertIn('current["probe_verified"]=True',source)
        self.assertIn('current["last_relay_uncertain"]=True',source)

    def test_inbound_relay_briefly_teaches_access_boundary_not_skills(self):
        target="6aef341a-d850-83ed-a3b2-c735a215bce3"
        body="Please examine a new question voluntarily."
        envelope=inbound_relay_envelope(CHAT,target,REQ,body)
        self.assertTrue(envelope.startswith("[Baton relay "+REQ))
        self.assertIn("from /c/"+CHAT,envelope)
        self.assertIn("to /c/"+target,envelope)
        self.assertIn("does NOT activate",envelope)
        self.assertIn("PAUSE_UI_WRITES",envelope)
        self.assertTrue(envelope.endswith("\n"+body))
        self.assertNotIn(NONCE,envelope)
        self.assertLess(len(envelope),4000)

    def test_inbound_relay_never_executes_or_promises_delivery(self):
        target="6aef341a-d850-83ed-a3b2-c735a215bce3"
        envelope=inbound_relay_envelope(CHAT,target,REQ,"One new request")
        self.assertIsNone(parse_assistant_tool_call(envelope,NONCE))
        self.assertIn("A reply is voluntary",envelope)
        self.assertIn("do not blindly retry",envelope)

    def test_inbound_relay_rejects_wrong_target_and_overlong_message(self):
        with self.assertRaises(ValueError):
            inbound_relay_envelope(CHAT,"other",REQ,"Valid message")
        with self.assertRaises(ValueError):
            inbound_relay_envelope(CHAT,CHAT,"wrong", "Valid message")
        with self.assertRaises(ValueError):
            inbound_relay_envelope(CHAT,CHAT,REQ,"a"*3001)

    def test_embedded_relay_uses_current_inbound_note(self):
        source=inspect.getsource(attach_model_bridge)
        self.assertIn("inbound_relay_envelope(source_chat,target,request",source)
        self.assertIn('"detail":"relay message too long"',source)
        self.assertIn('if ui_writes_paused():',source)


if __name__=="__main__":
    unittest.main()
