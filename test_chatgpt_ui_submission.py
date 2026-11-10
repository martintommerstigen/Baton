import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
from chatgpt_ui_driver import ChatGPTUIDriver, pause_active
from wake_adapter import PreSubmissionRejected

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
        with patch('chatgpt_ui_driver.pause_active') as pause:
            pause.return_value=False
            ChatGPTUIDriver(p,frozenset({CID})).submit_once(CID,'msg-1','hello')
        self.assertEqual(p.send.clicks,1)
        self.assertIn('[BATON-WAKE:msg-1]',p.editor.fills[0])
    def test_pause_after_fill_prevents_click(self):
        p=Page()
        with patch('chatgpt_ui_driver.pause_active') as pause:
            pause.return_value=True
            with self.assertRaises(PreSubmissionRejected):
                ChatGPTUIDriver(p,frozenset({CID})).submit_once(CID,'msg-1','hello')
        self.assertEqual(p.send.clicks,0)
    def test_existing_draft_untouched(self):
        p=Page();p.editor.text='unfinished user draft'
        with self.assertRaises(PreSubmissionRejected):
            ChatGPTUIDriver(p,frozenset({CID})).submit_once(CID,'msg-1','hello')
        self.assertEqual(p.editor.fills,[])
        self.assertEqual(p.send.clicks,0)
    def test_composer_normalization_rejected_before_click(self):
        # The adapter authorized a literal newline; a UI that silently
        # replaces it must not send a different body.
        p=Page()
        def normalized_fill(value):
            p.editor.fills.append(value)
            p.editor.text=value.replace("\n"," ")
        p.editor.fill=normalized_fill
        with patch('chatgpt_ui_driver.pause_active') as pause:
            pause.return_value=False
            with self.assertRaisesRegex(PreSubmissionRejected,'Composer content differs'):
                ChatGPTUIDriver(p,frozenset({CID})).submit_once(CID,'msg-1','hello')
        self.assertEqual(p.send.clicks,0)

    def test_concurrent_composer_edit_rejected_before_click(self):
        # A browser extension or user edit may mutate the draft after fill,
        # while the send button remains enabled.
        p=Page()
        def mutating_enabled():
            p.editor.text += "\nINJECTED"
            return True
        p.send.is_enabled=mutating_enabled
        with patch('chatgpt_ui_driver.pause_active') as pause:
            pause.return_value=False
            with self.assertRaisesRegex(RuntimeError,'Composer content differs'):
                ChatGPTUIDriver(p,frozenset({CID})).submit_once(CID,'msg-1','hello')
        self.assertEqual(p.send.clicks,0)

    def test_composer_exact_payload_still_sends(self):
        p=Page()
        with patch('chatgpt_ui_driver.pause_active') as pause:
            pause.return_value=False
            ChatGPTUIDriver(p,frozenset({CID})).submit_once(CID,'msg-1','line 1\nline 2')
        self.assertEqual(p.send.clicks,1)
        self.assertEqual(p.editor.text,'[BATON-WAKE:msg-1]\nline 1\nline 2')

    def test_dangling_pause_symlink_blocks_click(self):
        with tempfile.TemporaryDirectory() as d:
            marker = Path(d) / 'PAUSE_UI_WRITES'
            marker.symlink_to(Path(d) / 'missing-target')
            self.assertTrue(pause_active(marker))
            p = Page()
            with patch('chatgpt_ui_driver.PAUSE_FILE', marker):
                with self.assertRaisesRegex(PreSubmissionRejected, 'paused'):
                    ChatGPTUIDriver(p, frozenset({CID})).submit_once(CID, 'msg-1', 'hello')
            self.assertEqual(p.send.clicks, 0)

    def test_missing_or_symlinked_pause_parent_blocks_click(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for parent in (root / 'missing-parent', root / 'link-parent'):
                if parent.name == 'link-parent':
                    parent.symlink_to(root / 'missing-target')
                marker = parent / 'PAUSE_UI_WRITES'
                self.assertTrue(pause_active(marker))
                p = Page()
                with patch('chatgpt_ui_driver.PAUSE_FILE', marker):
                    with self.assertRaises(PreSubmissionRejected):
                        ChatGPTUIDriver(p, frozenset({CID})).submit_once(CID, 'msg-1', 'hello')
                self.assertEqual(p.send.clicks, 0)

    def test_pause_created_after_status_check_blocks_click(self):
        with tempfile.TemporaryDirectory() as d:
            marker = Path(d) / 'PAUSE_UI_WRITES'
            self.assertFalse(pause_active(marker))  # earlier gateway observation
            p = Page()
            def enable_and_pause():
                marker.touch()
                return True
            p.send.is_enabled = enable_and_pause
            with patch('chatgpt_ui_driver.PAUSE_FILE', marker):
                with self.assertRaises(PreSubmissionRejected):
                    ChatGPTUIDriver(p, frozenset({CID})).submit_once(CID, 'msg-1', 'hello')
            self.assertEqual(p.send.clicks, 0)

    def test_real_absent_pause_marker_allows_click(self):
        with tempfile.TemporaryDirectory() as d:
            marker = Path(d) / 'PAUSE_UI_WRITES'
            self.assertFalse(pause_active(marker))
            p = Page()
            with patch('chatgpt_ui_driver.PAUSE_FILE', marker):
                ChatGPTUIDriver(p, frozenset({CID})).submit_once(CID, 'msg-1', 'hello')
            self.assertEqual(p.send.clicks, 1)



if __name__=='__main__': unittest.main()
