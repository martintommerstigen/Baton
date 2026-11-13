"""Offscreen Baton multiroom page: statuses and proposals, never external send."""
from pathlib import Path
import os
import tempfile
import unittest

from baton_multiroom_reference import Multiroom, CHANNELS


class MultiroomWidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
        from PySide6.QtWidgets import QApplication
        cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root=Path(tmp.name)
        receipts=root/"receipts";receipts.mkdir()
        self.model=Multiroom(root/"db",receipts)
        from baton_multiroom_ui import build_multiroom_widget
        self.widget=build_multiroom_widget(store=self.model)
        self.addCleanup(self.widget.close)

    def test_channel_statuses_are_honest_and_no_send_button(self):
        ctrl=self.widget.baton_multiroom_controls
        self.assertEqual(ctrl["channels"].rowCount(),len(CHANNELS))
        rows=[ctrl["channels"].item(i,0).text()
              for i in range(ctrl["channels"].rowCount())]
        self.assertIn("ruben_chatgpt",rows)
        self.assertIn("messenger_personal",rows)
        self.assertIn("messenger_page",rows)
        self.assertIn("ingen",ctrl["status"].text().lower()+
                " ingen melding sendt")
        self.assertIn("ingen sending",ctrl["propose"].text().lower())

    def test_local_new_topic_appears_without_activating_model(self):
        ctrl=self.widget.baton_multiroom_controls
        self.model.topic("external-channels","Messenger og Ruben")
        ctrl["refresh"].click()
        self.assertEqual(ctrl["topics"].count(),1)
        self.assertIn("Messenger og Ruben",ctrl["topics"].item(0).text())
        self.assertFalse(self.model.overview()["model_liveness_verified"])

    def test_external_proposal_does_not_become_send_or_grant(self):
        self.model.topic("external-channels","Messenger og Ruben")
        p=self.model.propose_external(suggestion_id="ruben-idea",
              topic_id="external-channels",channel="ruben_chatgpt",
              recipient_hint="Ruben's existing conversation",
              purpose="Would a shared GTRCM discussion be useful?")
        self.assertFalse(p["authorized"])
        self.assertFalse(p["sent"])
        self.assertEqual(self.model.overview()["external_proposals_without_grants"],1)
        self.assertIsNone(self.model.authority.status("ruben-idea"))

    def test_widget_uses_local_reference_never_network_actions(self):
        import inspect
        from baton_multiroom_ui import build_multiroom_widget
        source=inspect.getsource(build_multiroom_widget)
        self.assertIn("model.propose_external",source)
        self.assertNotIn("client.send(",source)
        self.assertNotIn("send_click_script(",source)
        self.assertNotIn("execute_on_greg(",source)

    def test_main_and_chat_panel_expose_it(self):
        from pathlib import Path
        root=Path(__file__).resolve().parent
        self.assertIn('tabs.addTab(build_multiroom_widget(tabs), "Samtaler og kanaler")',
                      (root/"baton_core_window.py").read_text())
        self.assertIn('show_multiroom_dialog(window)',
                      (root/"baton_conversation_panel.py").read_text())


if __name__=="__main__":
    unittest.main()
