import json
import urllib.error
import unittest
from unittest.mock import Mock

from baton_model_clients import validate_endpoint, chat_completion


class _Reply:
    status = 200

    def __init__(self, content):
        self.content = content

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self, max_size):
        return json.dumps({"choices": [{"message": {"content": self.content}}]}).encode()


class ModelClientTests(unittest.TestCase):
    def test_local_ollama_endpoint(self):
        self.assertEqual(
            validate_endpoint("http://127.0.0.1:11434/v1/chat/completions"),
            "http://127.0.0.1:11434/v1/chat/completions"
        )

    def test_no_plain_http_to_remote(self):
        for endpoint in (
            "http://example.com/v1/chat/completions",
            "https://user:password@example.com/v1/chat/completions",
            "https://example.com/v1/chat/completions?token=hidden",
            "http://127.0.0.1:11434/admin",
            "ftp://example.com/v1/chat/completions",
        ):
            with self.subTest(endpoint=endpoint), self.assertRaises(ValueError):
                validate_endpoint(endpoint)

    def test_adapter_builds_structured_request(self):
        fake = Mock()
        fake.open.return_value = _Reply("Hei fra lokal modell")
        response = chat_completion(
            "http://127.0.0.1:11434/v1/chat/completions",
            "llama-local", "Hei, Baton", opener=fake
        )
        self.assertEqual(response, "Hei fra lokal modell")
        request = fake.open.call_args.args[0]
        self.assertEqual(request.method, "POST")
        data = json.loads(request.data)
        self.assertEqual(data["model"], "llama-local")
        self.assertEqual(data["messages"], [{"role":"user","content":"Hei, Baton"}])
        self.assertNotIn("tools", data)
        self.assertIsNone(request.get_header("Authorization"))

    def test_bearer_used_only_in_request(self):
        fake = Mock()
        fake.open.return_value = _Reply("ok")
        self.assertEqual(chat_completion(
            "https://example.com/v1/chat/completions",
            "remote-model", "hi", bearer="private-token", opener=fake
        ), "ok")
        request = fake.open.call_args.args[0]
        self.assertEqual(request.get_header("Authorization"), "Bearer private-token")

    def test_no_leak_when_provider_error(self):
        fake = Mock()
        fake.open.side_effect = urllib.error.HTTPError(
            "https://example.com/v1/chat/completions",
            403, "Authorization: Bearer private-secret", None, None
        )
        with self.assertRaises(RuntimeError) as error:
            chat_completion("https://example.com/v1/chat/completions",
                            "remote", "hi", bearer="private-secret", opener=fake)
        self.assertNotIn("private-secret", str(error.exception))

    def test_reject_invalid_fields(self):
        fake = Mock()
        with self.assertRaises(ValueError):
            chat_completion("http://localhost/v1/chat/completions",
                            "model", "", opener=fake)
        with self.assertRaises(ValueError):
            chat_completion("http://localhost/v1/chat/completions",
                            "model", "hi", bearer="bad\nInjected: yes", opener=fake)
        fake.open.assert_not_called()


if __name__ == "__main__":
    unittest.main()
