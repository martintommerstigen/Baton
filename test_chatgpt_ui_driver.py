import unittest
from chatgpt_ui_driver import conversation_id, ChatGPTUIDriver

CID='6af04e14-3e68-83eb-b53b-e4b352c84091'
OTHER='aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'

class Page:
    url='https://chatgpt.com/c/'+CID

class UITests(unittest.TestCase):
    def test_existing_conversation(self):
        self.assertEqual(conversation_id(Page.url),CID)
    def test_reject_wrong_origins(self):
        for url in ('https://evil.com/c/'+CID,'http://chatgpt.com/c/'+CID,
                    'https://chatgpt.com/','https://chatgpt.com/c/not-an-id',
                    'https://chatgpt.com/g/gpt-id'):
            with self.subTest(url=url),self.assertRaises(ValueError):
                conversation_id(url)
    def test_target_mismatch(self):
        d=ChatGPTUIDriver(Page(),frozenset({CID,OTHER}))
        with self.assertRaises(RuntimeError): d._check(OTHER)
    def test_not_allowlisted(self):
        d=ChatGPTUIDriver(Page(),frozenset())
        with self.assertRaises(PermissionError): d._check(CID)
    def test_empty_payload(self):
        d=ChatGPTUIDriver(Page(),frozenset({CID}))
        with self.assertRaises(ValueError): d.submit_once(CID,'id','')

if __name__=='__main__': unittest.main()
