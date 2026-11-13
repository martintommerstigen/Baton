import unittest
from run_chatgpt_wake_chain import select_pages

A='aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'
B='bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb'
class Page:
    def __init__(self,chat): self.url='https://chatgpt.com/c/'+chat
class Context:
    def __init__(self,pages): self.pages=pages
class Browser:
    def __init__(self,contexts): self.contexts=contexts

class ChainRunnerTests(unittest.TestCase):
    def test_two_existing_tabs(self):
        pages=select_pages(Browser([Context([Page(A),Page(B)])]),(A,B))
        self.assertEqual(set(pages),{A,B})
    def test_missing_target_rejected(self):
        with self.assertRaises(RuntimeError):
            select_pages(Browser([Context([Page(A)])]),(A,B))
    def test_duplicate_target_rejected(self):
        with self.assertRaises(RuntimeError):
            select_pages(Browser([Context([Page(A),Page(A),Page(B)])]),(A,B))

if __name__=='__main__': unittest.main()
