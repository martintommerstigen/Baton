import unittest
from unittest.mock import patch
from chatgpt_ui_driver import ChatGPTUIDriver

CID='6af04e14-3e68-83eb-b53b-e4b352c84091'

class FakeEditor:
    def __init__(self): self.text='';self.fills=[]
    def count(self): return 1
    def is_visible(self): return True
    def inner_text(self): return self.text
    def fill(self,value): self.text=value;self.fills.append(value)
class FakeSend:
    def __init__(self): self.clicks=0
    def count(self): return 1
    def is_enabled(self): return True
    def click(self): self.clicks+=1
class FakeUserTurns:
    def filter(self,has_text): return self
    def count(self): return 0
class Page:
    url='https://chatgpt.com/c/'+CID
    def __init__(self): self.editor=FakeEditor();self.send=FakeSend()
    def locator(self,selector):
        return {'#prompt-textarea':self.editor,
                '[data-testid="send-button"]':self.send,
                '[data-message-author-role="user"]':FakeUserTurns()}[selector]

class SubmissionTests(unittest.TestCase):
    def test_exactly_one_click(self):
        p=Page()
        with patch('chatgpt_ui_driver.PAUSE_FILE') as pause:
            pause.exists.return_value=False
            ChatGPTUIDriver(p,frozenset({CID})).submit_once(CID,'msg-1','hello')
        self.assertEqual(p.send.clicks,1)
        self.assertIn('[BATON-WAKE:msg-1]',p.editor.fills[0])
    def test_pause_after_fill_prevents_click(self):
        p=Page()
        with patch('chatgpt_ui_driver.PAUSE_FILE') as pause:
            pause.exists.return_value=True
            with self.assertRaises(RuntimeError):
                ChatGPTUIDriver(p,frozenset({CID})).submit_once(CID,'msg-1','hello')
        self.assertEqual(p.send.clicks,0)
    def test_existing_draft_untouched(self):
        p=Page();p.editor.text='unfinished user draft'
        with self.assertRaises(RuntimeError):
            ChatGPTUIDriver(p,frozenset({CID})).submit_once(CID,'msg-1','hello')
        self.assertEqual(p.editor.fills,[])
        self.assertEqual(p.send.clicks,0)

if __name__=='__main__': unittest.main()
