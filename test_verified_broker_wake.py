"""B1/B5 verified-peer bridge negatives; no browser or Greg interaction."""
import os
import sys
import types
import unittest
from unittest.mock import patch

from run_verified_broker_wake import (make_verified_broker_request,
                                       select_existing_tabs, execute_once)

A = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'
B = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb'


class VerifiedBridgeTests(unittest.TestCase):
    def test_reject_same_uid_or_root_before_import(self):
        for uid in (0, os.getuid(), -1):
            with self.subTest(uid=uid), self.assertRaises(ValueError):
                make_verified_broker_request('/safe/broker.sock', uid)

    def test_missing_b5_client_fails_closed(self):
        with patch.dict(sys.modules, {'remote_security': None}):
            with self.assertRaisesRegex(RuntimeError, 'not installed'):
                make_verified_broker_request('/safe/broker.sock', os.getuid() + 1)

    def test_verified_peer_called_with_distinct_uid_and_no_fallback(self):
        calls = []
        package = types.ModuleType('remote_security')
        package.__path__ = []
        module = types.ModuleType('remote_security.broker_peer')
        def peer(path, uid, envelope, **kwargs):
            calls.append((path, uid, envelope.copy(), kwargs))
            return {'state': 'admitted_not_delivered'}
        module.query_verified_broker = peer
        with patch.dict(sys.modules, {'remote_security': package,
                                      'remote_security.broker_peer': module}):
            request = make_verified_broker_request('/safe/broker.sock', os.getuid() + 1)
            self.assertEqual(request({'op': 'admit', 'message_id': 'm1'}),
                             {'state': 'admitted_not_delivered'})
            self.assertEqual(len(calls), 1)
            self.assertTrue(calls[0][3]['require_distinct_uid'])
            self.assertEqual(calls[0][1], os.getuid() + 1)
            with self.assertRaises(ValueError):
                request({'op': 'status'})
            self.assertEqual(len(calls), 1)

    def test_wrong_socket_path_rejected(self):
        with self.assertRaises(ValueError):
            make_verified_broker_request('relative.sock', os.getuid() + 1)

    def test_source_equals_target_rejected_without_browser(self):
        with self.assertRaises(ValueError):
            select_existing_tabs(None, A, A)

    def test_missing_or_duplicate_tab_rejected(self):
        class Page:
            def __init__(self, url): self.url = url
        class Context:
            pages = [Page('https://chatgpt.com/c/' + A),
                     Page('https://chatgpt.com/c/' + A),
                     Page('https://chatgpt.com/c/' + B)]
        class Browser:
            contexts = [Context()]
        with self.assertRaises(RuntimeError):
            select_existing_tabs(Browser(), A, B)

    def test_unverified_source_never_calls_broker_or_ui(self):
        class Source:
            def is_generating(self, _): return False
            def read_assistant_turn(self, *_): return 'ordinary response'
        class Target:
            def submit_once(self, *_): raise AssertionError('must not send')
        called = []
        def broker(request): called.append(request)
        with self.assertRaises(PermissionError):
            execute_once(None, Source(), Target(), A, B, 'turn-a', 'm1',
                         'harmless', broker, 0)
        self.assertEqual(called, [])

    def test_source_generating_never_calls_broker(self):
        class Source:
            def is_generating(self, _): return True
        called = []
        with self.assertRaises(RuntimeError):
            execute_once(None, Source(), object(), A, B, 'turn-a', 'm1',
                         'harmless', lambda req: called.append(req), 0)
        self.assertEqual(called, [])


if __name__ == '__main__':
    unittest.main()
