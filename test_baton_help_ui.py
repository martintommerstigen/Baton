"""Offscreen smoke tests of the real Baton HOWTO/FAQ widget and status card."""
from pathlib import Path
import os
import tempfile
import unittest

from baton_help_catalog import HelpCatalog
from baton_onboarding import connection_state, peer_quickstart, STATE_EXPLANATIONS


class OnboardingStateTests(unittest.TestCase):
    def test_plain_reply_does_not_prove_outbound_access(self):
        self.assertEqual(connection_state(exact_chat=False), "INBOUND_ONLY")
        self.assertEqual(connection_state(exact_chat=True), "BRIDGE_INACTIVE")
        self.assertEqual(connection_state(exact_chat=True,bridge_enabled=True),
                         "BRIDGE_STARTING")

    def test_ready_only_after_real_bridge_observation(self):
        self.assertEqual(connection_state(exact_chat=True,bridge_enabled=True,
                                         handshake_observed=True),"READY")
        self.assertEqual(connection_state(exact_chat=False,bridge_enabled=True,
                                         handshake_observed=True),"INBOUND_ONLY")

    def test_pause_and_uncertain_take_precedence(self):
        self.assertEqual(connection_state(exact_chat=True,bridge_enabled=True,
                                         handshake_observed=True,paused=True),"PAUSED")
        self.assertEqual(connection_state(exact_chat=True,bridge_enabled=True,
                                         handshake_observed=True,paused=True,
                                         uncertain=True),"UNCERTAIN")

    def test_every_state_explained(self):
        self.assertEqual(set(STATE_EXPLANATIONS),
                         {"INBOUND_ONLY","BRIDGE_INACTIVE","BRIDGE_STARTING",
                          "PAUSED","READY","UNCERTAIN"})

    def test_card_not_capability_or_nonce(self):
        with tempfile.TemporaryDirectory() as d:
            cat=HelpCatalog(Path(d)/"help.sqlite3")
            card=peer_quickstart(current_chat_id="6aef00a2-02d0-83ed-84a9-b2648808819a",
                                 paused=True,catalog=cat)
            self.assertIn("PAUSED",card)
            self.assertIn("BATON_CHAT_V1",card)
            self.assertIn("IKKE",card)
            self.assertNotIn("BATON_CHAT_V1 123",card)
            self.assertLess(len(card),5000)

    def test_card_cannot_use_invalid_conversation_id(self):
        with tempfile.TemporaryDirectory() as d:
            cat=HelpCatalog(Path(d)/"h.sqlite3")
            with self.assertRaises(ValueError):
                peer_quickstart(current_chat_id="../../etc",catalog=cat)

    def test_card_preserves_uncertain_outcome_instead_of_claiming_ready(self):
        with tempfile.TemporaryDirectory() as d:
            cat=HelpCatalog(Path(d)/"h.sqlite3")
            card=peer_quickstart(current_chat_id="6aef00a2-02d0-83ed-84a9-b2648808819a",
                                 observed_state="UNCERTAIN",paused=True,catalog=cat)
            self.assertIn("OBSERVERT KANALSTATUS: UNCERTAIN",card)
            self.assertLess(len(card),4000)

    def test_invalid_observed_status_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            cat=HelpCatalog(Path(d)/"h.sqlite3")
            with self.assertRaises(ValueError):
                peer_quickstart(observed_state="PERMANENTLY_CONNECTED",catalog=cat)


class WidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
        from PySide6.QtWidgets import QApplication
        cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store=HelpCatalog(Path(self.temp.name)/"help.sqlite3")
        from baton_help_ui import build_help_widget
        self.widget=build_help_widget(catalog=self.store)
        self.addCleanup(self.widget.close)

    def test_starts_with_searchable_howto_faq_and_status(self):
        controls=self.widget.baton_help_controls
        self.assertEqual(controls["tabs"].count(),2)
        self.assertGreaterEqual(controls["lists"]["howto"].count(),7)
        self.assertGreaterEqual(controls["lists"]["faq"].count(),8)
        self.assertEqual(controls["startcard"].objectName(),"baton-help-startcard")

    def test_search_filters_and_restores(self):
        ctrl=self.widget.baton_help_controls
        ctrl["search"].setText("utgående")
        self.assertGreaterEqual(ctrl["lists"]["faq"].count(),1)
        self.assertLess(ctrl["lists"]["howto"].count(),8)
        ctrl["search"].clear()
        self.assertGreaterEqual(ctrl["lists"]["howto"].count(),7)

    def test_copy_start_card_does_not_write_or_send(self):
        ctrl=self.widget.baton_help_controls
        before=len(self.store.list())
        ctrl["startcard"].click()
        text=self.app.clipboard().text()
        self.assertIn("BATON · STARTKORT",text)
        self.assertIn("Ingen",ctrl["status"].text())
        self.assertEqual(len(self.store.list()),before)

    def test_external_links_are_not_automatically_opened(self):
        ctrl=self.widget.baton_help_controls
        self.assertFalse(ctrl["details"]["howto"].openExternalLinks())
        self.assertFalse(ctrl["details"]["faq"].openExternalLinks())

    def test_change_is_reflected_without_recreating_widget(self):
        ctrl=self.widget.baton_help_controls
        doc=self.store.get("start-new-chat")
        p=self.store.propose(doc["slug"],doc["revision"],
                             doc["title"],doc["body"]+"\nKorrigert testinformasjon.",
                             "Varde reloaded reply 95ec38cc",
                             "Forskjell på innkommende og utgående sesjon")
        self.assertTrue(self.store.apply(p,doc["revision"])["applied"])
        ctrl["refresh"].click()
        ctrl["search"].setText("Korrigert testinformasjon.")
        self.assertEqual(ctrl["lists"]["howto"].count(),1)
        self.assertIn("Korrigert",ctrl["details"]["howto"].toPlainText())


if __name__ == "__main__":
    unittest.main()
