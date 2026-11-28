import io
import json
import unittest
from unittest.mock import patch
import baton_provider as b

class ProviderTests(unittest.TestCase):
    def test_two_providers(self):
        for name, (url, env) in b.PROVIDERS.items():
            with self.subTest(name=name), patch.dict('os.environ', {env: 'test-key'}, clear=True):
                plan = b.prepare(name, 'test-model', 'hei')
                def fake(req, timeout):
                    self.assertEqual(req.full_url, url)
                    self.assertEqual(req.get_header('Authorization'), 'Bearer test-key')
                    self.assertEqual(json.loads(req.data)['messages'][0]['content'], 'hei')
                    return io.BytesIO(json.dumps({'id':'test-response','choices':[{'finish_reason':'stop','message':{'content':'hallo'}}]}).encode())
                self.assertEqual(b.call(plan, allow_cost=True, opener=fake)['text'], 'hallo')
    def test_no_approval(self):
        with self.assertRaises(ValueError):
            b.call(b.prepare('gemini','m','hi'), opener=lambda *a,**k: self.fail('network'))
    def test_missing_key(self):
        with patch.dict('os.environ', {}, clear=True), self.assertRaises(ValueError):
            b.call(b.prepare('deepseek','m','hi'), allow_cost=True, opener=lambda *a,**k: self.fail('network'))
    def test_incomplete(self):
        with patch.dict('os.environ', {'GEMINI_API_KEY':'test'}, clear=True), self.assertRaises(ValueError):
            b.call(b.prepare('gemini','m','hi'), allow_cost=True, opener=lambda *a,**k: io.BytesIO(b'{"choices":[{"finish_reason":"length","message":{"content":"partial"}}]}'))
    def test_timeout_no_retry(self):
        calls=[]
        def fail(*a,**k):
            calls.append(1)
            raise TimeoutError()
        with patch.dict('os.environ', {'DEEPSEEK_API_KEY':'test'}, clear=True), self.assertRaises(TimeoutError):
            b.call(b.prepare('deepseek','m','hi'), allow_cost=True, opener=fail)
        self.assertEqual(calls,[1])
    def test_bad_prompt(self):
        for prompt in ('','ø'*8001):
            with self.assertRaises(ValueError): b.prepare('gemini','m',prompt)
    def test_redirect(self):
        self.assertIsNone(b.NoRedirect().redirect_request(None,None,302,'',{},'https://example.org'))

if __name__ == '__main__': unittest.main()
