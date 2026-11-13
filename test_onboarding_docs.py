"""Offline regression checks for Baton newcomer entrypoints (stdlib only).

The link check deliberately covers local Markdown file links, not external GitHub
branches, PRs, access permissions or the current Greg installation.
"""
from pathlib import Path
from urllib.parse import unquote, urlsplit
import re
import unittest

ROOT = Path(__file__).resolve().parent
ENTRYPOINTS = ("START_HERE.md", "docs/NEW_LLM_90_SECOND.md")
MARKDOWN_LINK = re.compile(r"\[[^\]]+\]\(([^)\s]+)\)")
REFERENCE_DEFINITION = re.compile(
    r"^[ \t]{0,3}\[[^\]\n]+\]:[ \t]*(?:<([^>\n]+)>|([^\s]+))", re.MULTILINE
)


def local_file_links(source):
    """Yield (link, resolved target) for relative Markdown file links."""
    text = source.read_text(encoding="utf-8")
    # Reference-style Markdown links were previously invisible to this check.
    # Validate every local definition, including unused definitions, so a later
    # edit cannot silently activate a broken source route.
    links = [m.group(1) for m in MARKDOWN_LINK.finditer(text)]
    links.extend((m.group(1) or m.group(2)) for m in REFERENCE_DEFINITION.finditer(text))
    for link in links:
        parsed = urlsplit(link)
        if parsed.scheme or parsed.netloc or not parsed.path or link.startswith("#"):
            continue
        yield link, (source.parent / unquote(parsed.path)).resolve()


class OnboardingDocsTest(unittest.TestCase):
    def test_newcomer_entrypoints(self):
        for relpath in ENTRYPOINTS:
            with self.subTest(path=relpath):
                text = (ROOT / relpath).read_text(encoding="utf-8")
                self.assertNotIn(r"\n", text, "Literal backslash-n breaks Markdown tables/paragraphs")
                self.assertIn("PAUSE_UI_WRITES", text)
                self.assertIn("Core", text)
                self.assertIn("GTRCM", text)

    def test_reference_style_missing_original_is_detected(self):
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as temp:
            card = Path(temp) / "newcomer.md"
            card.write_text("[Read the original][source]\n\n[source]: missing-original.md\n", encoding="utf-8")
            links = list(local_file_links(card))
            self.assertEqual(len(links), 1)
            self.assertEqual(links[0][0], "missing-original.md")
            self.assertFalse(links[0][1].exists())

    def test_start_links_to_newcomer_card(self):
        self.assertIn(
            "docs/NEW_LLM_90_SECOND.md",
            (ROOT / "START_HERE.md").read_text(encoding="utf-8"),
        )

    def test_relative_entrypoint_links_resolve(self):
        for relpath in ENTRYPOINTS:
            source = ROOT / relpath
            for link, target in local_file_links(source):
                with self.subTest(source=relpath, link=link):
                    self.assertTrue(
                        target.is_relative_to(ROOT),
                        f"Relative link escapes repository: {link}",
                    )
                    self.assertTrue(
                        target.is_file(),
                        f"Broken local newcomer link in {relpath}: {link}",
                    )


if __name__ == "__main__":
    unittest.main()
