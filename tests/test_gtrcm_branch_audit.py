"""Offline falsifiers for read-only GTRCM branch coverage; no network or UI."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / "tools" / "gtrcm_branch_audit.py"
spec = importlib.util.spec_from_file_location("gtrcm_branch_audit", SOURCE)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class FakeGitHub:
    def __init__(self, names=("main", "RustWorld"), mutate=False, truncated=False):
        self.names, self.mutate, self.truncated = names, mutate, truncated
        self.scans = 0

    def __call__(self, path):
        if "/branches?" in path:
            page = int(path.split("page=")[-1])
            if page == 1:
                self.scans += 1
                names = self.names if not (self.mutate and self.scans > 1) else self.names + ("new",)
                return [{"name": name, "commit": {"sha": f"{i+1:040x}"}}
                        for i, name in enumerate(names)]
            return []
        if "/git/trees/" in path:
            return {"truncated": self.truncated, "tree": [
                {"type": "blob", "path": "README.md"},
                {"type": "blob", "path": "research/old/NEG.md"},
                {"type": "blob", "path": "image.png"}]}
        if "/commits/" in path:
            return {"commit": {"committer": {"date": "2026-11-10T00:00:00Z"}}}
        raise AssertionError(path)


class InventoryTests(unittest.TestCase):
    def test_complete_inventory_does_not_claim_content_read(self):
        result = audit.collect(FakeGitHub())
        self.assertEqual((result["branch_count"], result["tree_indexed"], result["content_read"]), (2, 2, 0))
        self.assertEqual(result["branches"][0]["files_total"], 3)
        self.assertIn("research/old/NEG.md", result["branches"][0]["relevant_paths"])
        self.assertEqual(result["branches"][0]["commit_date"], "2026-11-10T00:00:00Z")

    def test_changed_branch_snapshot_is_not_published(self):
        with self.assertRaisesRegex(audit.IncompleteInventory, "changed"):
            audit.collect(FakeGitHub(mutate=True))

    def test_truncated_tree_is_not_silently_complete(self):
        with self.assertRaisesRegex(audit.IncompleteInventory, "incomplete tree"):
            audit.collect(FakeGitHub(truncated=True))

    def test_duplicate_branch_across_pages_rejected(self):
        original = audit.PAGE_SIZE
        try:
            audit.PAGE_SIZE = 1
            def fetch(path):
                page = int(path.split("page=")[-1])
                if page in (1, 2):
                    return [{"name": "same", "commit": {"sha": "a"*40}}]
                return []
            with self.assertRaisesRegex(audit.IncompleteInventory, "duplicate"):
                audit.scan_branches(fetch)
        finally:
            audit.PAGE_SIZE = original

    def test_invalid_sha_rejected(self):
        with self.assertRaises(audit.IncompleteInventory):
            audit.scan_branches(lambda _: [{"name": "main", "commit": {"sha": "bad"}}])

    def test_output_refuses_existing_path(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)/"already.json"
            p.write_text("keep")
            with patch.object(audit, "github_fetch", return_value=FakeGitHub()):
                self.assertEqual(audit.main(["--output", str(p)]), 2)
            self.assertEqual(p.read_text(), "keep")

    def test_symlink_output_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            target = Path(td)/"target"
            target.write_text("keep")
            p = Path(td)/"link"
            p.symlink_to(target)
            with patch.object(audit, "github_fetch", return_value=FakeGitHub()):
                self.assertEqual(audit.main(["--output", str(p)]), 2)
            self.assertEqual(target.read_text(), "keep")


if __name__ == "__main__":
    unittest.main()
