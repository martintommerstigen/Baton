import tempfile
from unittest import mock
import unittest
from pathlib import Path
from baton_dual_model_sessions import connect, select_model, route_message


class DualModelSessionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = connect(Path(self.tmp.name) / "nested" / "sessions.sqlite")

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def test_local_never_receives_api_key(self):
        select_model(self.db, "s", "local", "llama3.2")
        calls = []
        def fake(url, model, prompt, **kwargs):
            calls.append((url, model, prompt, kwargs))
            return "local reply"
        self.assertEqual(route_message(self.db, "s", "hi", api_key="secret", sender=fake), "local reply")
        self.assertIn("127.0.0.1", calls[0][0])
        self.assertIsNone(calls[0][3]["bearer"])

    def test_openai_requires_key(self):
        select_model(self.db, "s", "openai", "gpt-4.1-mini")
        with mock.patch.dict("os.environ", {"OPENAI_API_KEY": ""}):
            with self.assertRaises(ValueError):
                route_message(self.db, "s", "hi")

    def test_switch_same_session(self):
        select_model(self.db, "s", "local", "llama3.2")
        select_model(self.db, "s", "openai", "gpt-4.1-mini")
        calls = []
        def fake(url, model, prompt, **kwargs):
            calls.append((url, model, kwargs["bearer"]))
            return "ok"
        self.assertEqual(route_message(self.db, "s", "hi", api_key="secret", sender=fake), "ok")
        self.assertEqual(calls, [("https://api.openai.com/v1/chat/completions", "gpt-4.1-mini", "secret")])

    def test_reject_unconfigured_session(self):
        with self.assertRaises(ValueError):
            route_message(self.db, "missing", "hi", sender=lambda *a, **k: "bad")

    def test_reject_unknown_backend(self):
        with self.assertRaises(ValueError):
            select_model(self.db, "s", "arbitrary", "model")


if __name__ == "__main__":
    unittest.main()
