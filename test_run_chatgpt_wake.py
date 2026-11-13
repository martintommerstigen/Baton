import unittest
from run_chatgpt_wake import local_cdp

class RunnerSafetyTests(unittest.TestCase):
    def test_local_only(self):
        self.assertEqual(local_cdp('http://127.0.0.1:9222'),'http://127.0.0.1:9222')
        for value in ('http://example.com:9222','https://127.0.0.1:9222',
                      'http://user:pass@127.0.0.1:9222'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                local_cdp(value)

if __name__=='__main__': unittest.main()
