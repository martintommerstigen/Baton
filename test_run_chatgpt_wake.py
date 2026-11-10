import unittest
from unittest.mock import patch
from run_chatgpt_wake import local_cdp, main

class RunnerSafetyTests(unittest.TestCase):
    def test_local_only(self):
        self.assertEqual(local_cdp('http://127.0.0.1:9222'),'http://127.0.0.1:9222')
        for value in ('http://example.com:9222','https://127.0.0.1:9222',
                      'http://user:pass@127.0.0.1:9222'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                local_cdp(value)

    def test_fail_closed_pause_preflight_before_browser(self):
        args=['--db','offline.sqlite3','--id','msg-1','--target',
              'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb','--source',
              'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa','--body','test']
        with patch('run_chatgpt_wake.pause_active', return_value=True):
            with self.assertRaisesRegex(RuntimeError, 'paused'):
                main(args)


if __name__=='__main__': unittest.main()
