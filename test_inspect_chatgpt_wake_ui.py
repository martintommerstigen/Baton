import unittest
from inspect_chatgpt_wake_ui import inspect_browser

A="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
B="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"

class Locator:
    def __init__(self,n=1,ids=None): self.n=n;self.ids=ids or []
    def count(self): return self.n
    def is_visible(self): return True
    def is_enabled(self): return True
    def nth(self,i): return Turn(self.ids[i] if i<len(self.ids) else None)
class Turn:
    def __init__(self,mid): self.mid=mid
    def get_attribute(self,key): return self.mid if key=="data-message-id" else None
class Page:
    def __init__(self,cid,ids=("turn1",)):
        self.url="https://chatgpt.com/c/"+cid
        self.ids=ids
    def locator(self,selector):
        if selector=='[data-message-author-role="assistant"]':
            return Locator(len(self.ids),self.ids)
        return Locator()
class Context:
    def __init__(self,pages): self.pages=pages
class Browser:
    def __init__(self,pages): self.contexts=[Context(pages)]

class PreflightTests(unittest.TestCase):
    def test_ready(self):
        r=inspect_browser(Browser([Page(A),Page(B)]),[A,B])
        self.assertTrue(r["ready"])
        self.assertEqual(r["targets"][A]["inspection"]["assistant_turn_ids_present"],1)
    def test_missing_target(self):
        r=inspect_browser(Browser([Page(A)]),[A,B])
        self.assertFalse(r["ready"])
        self.assertEqual(r["targets"][B]["tab_count"],0)
    def test_duplicate_tab(self):
        r=inspect_browser(Browser([Page(A),Page(A)]),[A])
        self.assertFalse(r["ready"])
        self.assertEqual(r["targets"][A]["tab_count"],2)
    def test_missing_assistant_ids(self):
        r=inspect_browser(Browser([Page(A,(None,))]),[A])
        self.assertFalse(r["ready"])

if __name__=="__main__": unittest.main()
