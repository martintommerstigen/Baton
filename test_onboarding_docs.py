"""Regression checks for the two public newcomer entrypoints (stdlib only)."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent

class OnboardingDocsTest(unittest.TestCase):
    def test_newcomer_entrypoints(self):
        for relpath in ("START_HERE.md", "docs/NEW_LLM_90_SECOND.md"):
            with self.subTest(path=relpath):
                text = (ROOT / relpath).read_text(encoding="utf-8")
                self.assertNotIn(r"\n", text, "Literal backslash-n breaks Markdown tables/paragraphs")
                self.assertIn("PAUSE_UI_WRITES", text)
                self.assertIn("Core", text)
                self.assertIn("GTRCM", text)

    def test_start_links_to_newcomer_card(self):
        self.assertIn(
            "docs/NEW_LLM_90_SECOND.md",
            (ROOT / "START_HERE.md").read_text(encoding="utf-8"),
        )

if __name__ == "__main__":
    unittest.main()
