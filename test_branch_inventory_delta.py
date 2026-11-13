"""Offline negative and pagination tests for the read-only branch delta helper."""
import io
import json
import unittest
from urllib.error import HTTPError

import branch_inventory_delta as mod


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self
    def __exit__(self, *args):
        self.close()


class BranchInventoryDeltaTests(unittest.TestCase):
    def test_pagination_at_exact_hundred_boundary(self):
        calls = []
        def opener(req, timeout):
            calls.append((req.full_url, timeout))
            items = [{"name": f"branch-{i}"} for i in range(100)] if len(calls) == 1 else [{"name": "branch-100"}]
            return FakeResponse(json.dumps(items).encode())
        names = mod.fetch_branches("owner/repo", opener=opener)
        self.assertEqual(len(names), 101)
        self.assertEqual(len(calls), 2)
        self.assertIn("page=2", calls[1][0])

    def test_changed_and_deleted_are_distinct(self):
        snapshot = {"repository": "owner/repo", "branch_count": 2, "branches": ["main", "old"]}
        diff = mod.compare(snapshot, ["main", "new"], "owner/repo")
        self.assertEqual(diff["added_since_snapshot"], ["new"])
        self.assertEqual(diff["missing_since_snapshot"], ["old"])

    def test_snapshot_integrity_and_repo_mismatch(self):
        snapshot = {"repository": "owner/repo", "branch_count": 2, "branches": ["main", "main"]}
        with self.assertRaises(ValueError):
            mod.compare(snapshot, ["main"], "owner/repo")
        with self.assertRaises(ValueError):
            mod.compare(snapshot, ["main"], "other/repo")

    def test_malformed_live_response_and_bad_repo(self):
        with self.assertRaises(ValueError):
            mod.fetch_branches("owner/repo?token=oops")
        with self.assertRaises(ValueError):
            mod.fetch_branches("owner/repo", opener=lambda *a, **k: FakeResponse(b'{"message":"Not Found"}'))

    def test_auth_header_is_not_embedded_in_error_url(self):
        def denied(req, timeout):
            self.assertNotIn("test-secret", req.full_url)
            self.assertEqual(req.get_header("Authorization"), "Bearer test-secret")
            raise HTTPError(req.full_url, 403, "Forbidden", {}, None)
        with self.assertRaises(HTTPError) as err:
            mod.fetch_branches("owner/private", token="test-secret", opener=denied)
        self.assertNotIn("test-secret", str(err.exception))


if __name__ == "__main__":
    unittest.main()
