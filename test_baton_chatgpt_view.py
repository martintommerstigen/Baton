import unittest
from baton_chatgpt_view import conversation_url,is_chatgpt_conversation_url

class EmbeddedChatGPTTests(unittest.TestCase):
    ID="6aef828e-0150-83eb-bbac-061f79a8fd4a"
    def test_known_conversation(self):
        url=conversation_url(self.ID)
        self.assertTrue(is_chatgpt_conversation_url(url,self.ID))
    def test_wrong_chat(self):
        self.assertFalse(is_chatgpt_conversation_url(conversation_url(self.ID), "6aef341a-d850-83ed-a3b2-c735a215bce3"))
    def test_reject_host_spoofing(self):
        self.assertFalse(is_chatgpt_conversation_url("https://chatgpt.com.evil.invalid/c/"+self.ID,self.ID))
    def test_reject_query_and_fragment(self):
        self.assertFalse(is_chatgpt_conversation_url(conversation_url(self.ID)+"?x=1",self.ID))
    def test_reject_path_injection(self):
        with self.assertRaises(ValueError):
            conversation_url(self.ID+"/../")
    def test_reject_empty_id(self):
        with self.assertRaises(ValueError):
            conversation_url("")

if __name__=="__main__":
    unittest.main()
