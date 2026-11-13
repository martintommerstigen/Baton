import unittest
from baton_conversation_panel import chat_id_from_url
from baton_chatgpt_view import conversation_url

class ConversationPanelTests(unittest.TestCase):
    CHAT="6af04e14-3e68-83eb-b53b-e4b352c84091"

    def test_existing_chat_address(self):
        self.assertEqual(chat_id_from_url(conversation_url(self.CHAT)), self.CHAT)

    def test_root_is_not_conversation(self):
        self.assertIsNone(chat_id_from_url("https://chatgpt.com/"))

    def test_wrong_origin_and_credentials_denied(self):
        for url in [
            "https://chatgpt.com.evil.test/c/"+self.CHAT,
            "http://chatgpt.com/c/"+self.CHAT,
            "https://user@chatgpt.com/c/"+self.CHAT,
            "https://evil.invalid/c/"+self.CHAT,
            "https://chatgpt.com:444/c/"+self.CHAT
        ]:
            with self.subTest(url=url):
                self.assertIsNone(chat_id_from_url(url))

    def test_query_fragment_denied(self):
        self.assertIsNone(chat_id_from_url(conversation_url(self.CHAT)+"?x=y"))
        self.assertIsNone(chat_id_from_url(conversation_url(self.CHAT)+"#unsafe"))

    def test_invalid_values(self):
        for value in [None, 32, {}, "", "https://chatgpt.com/c/not-an-id"]:
            with self.subTest(value=value):
                self.assertIsNone(chat_id_from_url(value))

if __name__ == "__main__":
    unittest.main()
