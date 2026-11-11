from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from baton_selected_context import load_selected_context, with_selected_context, snapshot_chatgpt_turn


class SelectedContextTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_explicit_text_context_and_unchanged_history(self):
        path = self.root / "GTRCM.md"
        path.write_text("Noe blir noe når det er noe for noe.", encoding="utf-8")
        ctx = load_selected_context(path)
        self.assertEqual(ctx["name"], "GTRCM.md")
        self.assertEqual(ctx["bytes"], len(path.read_bytes()))
        history = [{"role":"user","content":"Hva er GTRCM?"}]
        result = with_selected_context(history, ctx)
        self.assertEqual(len(result), 2)
        self.assertIn("Brukervalgte lokale bakgrunnsopplysninger", result[0]["content"])
        self.assertIn("Noe blir noe", result[0]["content"])
        self.assertIn("ikke ChatGPT-minne", result[0]["content"])
        self.assertEqual(history, [{"role":"user","content":"Hva er GTRCM?"}])
        self.assertEqual(with_selected_context(history, None), history)

    def test_no_implicit_scan_or_url(self):
        path = self.root / "secret.env"
        path.write_text("SECRET=must-not-send", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Markdown"):
            load_selected_context(path)

    def test_no_symlink_to_secret(self):
        outside = self.root / "secret.txt"
        outside.write_text("SECRET", encoding="utf-8")
        link = self.root / "alias.txt"
        link.symlink_to(outside)
        with self.assertRaisesRegex(ValueError, "lenke"):
            load_selected_context(link)

    def test_reject_binary_and_large_or_empty(self):
        path = self.root / "context.txt"
        path.write_bytes(b"\x00hidden")
        with self.assertRaisesRegex(ValueError, "Ugyldig"):
            load_selected_context(path)
        path.write_text("A"*33000)
        with self.assertRaisesRegex(ValueError, "stor"):
            load_selected_context(path)
        path.write_text(" ")
        with self.assertRaisesRegex(ValueError, "1–12000"):
            load_selected_context(path)

    def test_reject_fake_context_and_preserve_unicode(self):
        with self.assertRaises(ValueError):
            with_selected_context([{"role":"user","content":"Hei"}], {"name":"a.txt"})
        text = "Individuasjon og Gaia: økologisk relasjonering"
        path = self.root / "norsk.md"
        path.write_text(text)
        self.assertIn(text, load_selected_context(path)["text"])


    def test_send_snapshot_is_immune_to_later_file_selection(self):
        first = {"name": "first.md", "text": "ONLY-FIRST-CONTEXT"}
        second = {"name": "second.md", "text": "ONLY-SECOND-CONTEXT"}
        history = [{"role": "assistant", "content": "Previous reply"}]
        sent, request = snapshot_chatgpt_turn(history, "New question", first)
        # Simulate UI replacing its selection before the worker starts.
        selected = second
        first["text"] = "CHANGED-AFTER-SEND"
        first["name"] = "changed.md"
        self.assertIs(selected, second)
        self.assertIn("ONLY-FIRST-CONTEXT", request[0]["content"])
        self.assertIn("first.md", request[0]["content"])
        self.assertNotIn("ONLY-SECOND-CONTEXT", request[0]["content"])
        self.assertNotIn("CHANGED-AFTER-SEND", request[0]["content"])
        self.assertEqual(sent[-1], {"role": "user", "content": "New question"})
        self.assertEqual(history, [{"role": "assistant", "content": "Previous reply"}])

    def test_send_without_context_still_has_new_turn(self):
        sent, request = snapshot_chatgpt_turn([], "Hei", None)
        self.assertEqual(sent, [{"role": "user", "content": "Hei"}])
        self.assertEqual(request, sent)
        self.assertIsNot(request, sent)
        with self.assertRaises(ValueError):
            snapshot_chatgpt_turn([], "   ", None)


if __name__ == "__main__":
    unittest.main()
