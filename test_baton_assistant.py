"""CLI smoke tests; no network, no real API keys."""
import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch
from baton_assistant import main


class AssistantCLITests(unittest.TestCase):
    def test_select_and_status(self):
        with tempfile.TemporaryDirectory() as d:
            db = str(Path(d) / "state.sqlite")
            with redirect_stdout(io.StringIO()):
                main(["--db", db, "use", "test", "local", "llama3.2"])
            out = io.StringIO()
            with redirect_stdout(out):
                main(["--db", db, "status", "test"])
            self.assertEqual(out.getvalue().strip(), "local: llama3.2")

    def test_send_via_local_without_network(self):
        with tempfile.TemporaryDirectory() as d:
            db = str(Path(d) / "state.sqlite")
            with redirect_stdout(io.StringIO()):
                main(["--db", db, "use", "test", "local", "llama3.2"])
            out = io.StringIO()
            with patch("baton_assistant.route_message", return_value="reply") as send:
                with redirect_stdout(out):
                    main(["--db", db, "ask", "test", "hello"])
            send.assert_called_once()
            self.assertEqual(out.getvalue().strip(), "reply")


if __name__ == "__main__":
    unittest.main()
