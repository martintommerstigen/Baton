"""Direct existing-conversation routing is opt-in and does not use GitHub."""
import inspect
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from baton_existing_chat_tab import (
    browser_profile_directory, describe_connection, attach_existing_conversation_tab
)
from baton_model_bridge import attach_model_bridge
from baton_conversation_panel import attach_baton_panel


class BatonExistingConversationTests(unittest.TestCase):
    def test_profile_preserves_existing_qt_login_not_browser_cookies(self):
        with TemporaryDirectory() as root:
            target = browser_profile_directory(root)
            self.assertEqual(
                target, Path(root) / ".local/share/baton/chatgpt-profile"
            )

    def test_actual_existing_chat_not_just_authenticated_new_model(self):
        info = describe_connection()
        self.assertEqual(info["conversation"], "existing-chatgpt-chat")
        self.assertEqual(info["transport"], "direct-local-core-dom-bridge")
        self.assertIs(info["github_runtime"], False)
        self.assertIs(info["native_chatgpt_mcp"], False)
        self.assertIs(info["automatic_wake"], False)
        self.assertIs(info["user_opt_in_required"], True)

    def test_embedded_browser_reuses_real_conversation_panel(self):
        source = inspect.getsource(attach_existing_conversation_tab)
        self.assertIn("attach_baton_panel(browser, view, page)", source)
        self.assertIn('view.setUrl(QUrl("https://chatgpt.com/"))', source)
        self.assertIn("button.clicked.connect(open_existing)", source)
        self.assertIn("QWebEngineProfile", source)
        self.assertNotIn("baton_github_bus", source)
        self.assertNotIn("chatgpt_chat(", source)

    def test_existing_chat_panel_requires_manual_opt_in(self):
        source = inspect.getsource(attach_model_bridge)
        self.assertIn("auto_enable=False", source)
        self.assertIn("if not auto_enable:", source)
        self.assertIn("chat_id and auto_enable", source)
        self.assertIn("if ok and auto_enable", source)
        panel = inspect.getsource(attach_baton_panel)
        self.assertIn("attach_model_bridge(layout, view, page, dock, auto_enable=False)", panel)
        self.assertIn("manual_begin", source)
        self.assertIn("start.clicked.connect(manual_begin)", source)
        tab = inspect.getsource(attach_existing_conversation_tab)
        self.assertIn("Brave – bruk akkurat denne eksisterende ChatGPT-samtalen", tab)


if __name__ == "__main__":
    unittest.main()
