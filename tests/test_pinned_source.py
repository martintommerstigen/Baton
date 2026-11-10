"""B5/B2 source allowlist, local durable receipt and negative file tests."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from remote_security.pinned_source import (
    capture_pinned_source, verify_pinned_source, _policy_entry,
    JobRejected, UntrustedReceipt, MAX_SOURCE,
)
from remote_security.research_jobs import ResearchJobs


def blob_sha(raw):
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


class PinnedSourceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.base.chmod(0o700)
        self.root = self.base / "archive"
        self.source_dir = self.root / "source" / "Dokumenter" / "kindergarden" / "src"
        self.source_dir.mkdir(parents=True)
        self.source = self.source_dir / "world.rs"
        self.raw = b"pub fn step() {}\n"
        self.source.write_bytes(self.raw)
        self.policy = {"rustworld-world": {
            "path": "source/Dokumenter/kindergarden/src/world.rs",
            "git_blob_sha1": blob_sha(self.raw),
            "commit_sha": "a" * 40, "branch": "RustWorld",
        }}
        self.key = b"K" * 32
        self.db = self.base / "jobs.db"
        self.jobs = ResearchJobs(self.db, self.key, {"RustWorld": ["sha256-echo"]})

    def capture(self, job_id="source001"):
        return capture_pinned_source(self.jobs, str(self.root), self.policy, "rustworld-world", job_id)

    def test_complete_pinned_read_and_durable_audit_after_restart(self):
        bundle = self.capture()
        c = bundle["capture"]
        self.assertEqual(bundle["source_text"], self.raw.decode())
        self.assertEqual(c["git_blob_sha1"], blob_sha(self.raw))
        self.assertEqual(c["content_sha256"], hashlib.sha256(self.raw).hexdigest())
        self.assertEqual(c["evidence"], "local_bytes_match_pinned_blob_not_commit_or_host_attestation")
        self.assertEqual(bundle["job"]["receipt"]["exit_status"], 0)
        self.assertEqual(bundle["job"]["receipt"]["command"], "sha256-echo")
        auditor = ResearchJobs(self.db, self.key, {"RustWorld": ["sha256-echo"]}, audit_only=True)
        self.assertEqual(verify_pinned_source(auditor, self.policy, bundle)["state"],
                         "verified_local_pinned_blob_only")

    def test_replay_refused_and_previous_receipt_unchanged(self):
        self.capture()
        with self.assertRaises(JobRejected):
            self.capture()
        self.assertEqual(self.jobs.audit("RustWorld", "source001")["state"], "completed_local_only")

    def test_mutated_source_rejected_before_job_reservation(self):
        self.source.write_bytes(b"pub fn altered() {}\n")
        with self.assertRaises(JobRejected):
            self.capture()
        self.assertEqual(self.jobs.audit("RustWorld", "source001")["state"], "not_found_not_proof_of_nonexecution")

    def test_symlink_file_rejected(self):
        target = self.source_dir / "original.rs"
        self.source.rename(target)
        self.source.symlink_to(target)
        with self.assertRaises(OSError):
            self.capture()

    def test_symlink_parent_rejected(self):
        moved = self.root / "real_kindergarden"
        (self.root / "source" / "Dokumenter" / "kindergarden").rename(moved)
        (self.root / "source" / "Dokumenter" / "kindergarden").symlink_to(moved, target_is_directory=True)
        with self.assertRaises(OSError):
            self.capture()

    def test_traversal_absolute_and_double_slash_rejected(self):
        for value in ("/etc/passwd", "source/../etc/passwd", "source//Dokumenter/x",
                      "source/Dokumenter/./kindergarden/src/world.rs"):
            p = dict(self.policy["rustworld-world"], path=value)
            with self.subTest(value=value), self.assertRaises(JobRejected):
                _policy_entry(p)

    def test_wrong_branch_or_commit_rejected(self):
        for field, value in (("branch", "main"), ("commit_sha", "wrong"),
                             ("git_blob_sha1", "z" * 40)):
            p = dict(self.policy["rustworld-world"], **{field: value})
            with self.subTest(field=field), self.assertRaises(JobRejected):
                _policy_entry(p)

    def test_unknown_source_id_rejected(self):
        with self.assertRaises(JobRejected):
            capture_pinned_source(self.jobs, str(self.root), self.policy, "not-allowed", "source002")

    def test_nonallowlisted_project_route_rejected(self):
        wrong = ResearchJobs(self.base / "other.db", self.key, {"GTRCM": ["sha256-echo"]})
        with self.assertRaises(JobRejected):
            capture_pinned_source(wrong, str(self.root), self.policy, "rustworld-world", "source003")

    def test_unsafe_writable_parent_rejected(self):
        self.source_dir.chmod(0o777)
        with self.assertRaises(JobRejected):
            self.capture()

    def test_hardlink_rejected(self):
        os.link(self.source, self.source_dir / "alias.rs")
        with self.assertRaises(JobRejected):
            self.capture()

    def test_oversized_source_rejected(self):
        self.source.write_bytes(b"x" * (MAX_SOURCE + 1))
        with self.assertRaises(JobRejected):
            self.capture()

    @unittest.skipUnless(hasattr(os, "mkfifo"), "POSIX only")
    def test_fifo_rejected_without_blocking(self):
        self.source.unlink()
        os.mkfifo(self.source)
        with self.assertRaises(JobRejected):
            self.capture()

    def test_forged_capture_mac_rejected(self):
        bundle = self.capture()
        bundle["capture_mac"] = "0" * 64
        with self.assertRaises(UntrustedReceipt):
            verify_pinned_source(self.jobs, self.policy, bundle)

    def test_modified_source_text_and_receipt_rejected(self):
        bundle = self.capture()
        for field, value in (("source_text", "forged"), ("job", {"receipt": {}})):
            forged = deepcopy(bundle)
            forged[field] = value
            with self.subTest(field=field), self.assertRaises(UntrustedReceipt):
                verify_pinned_source(self.jobs, self.policy, forged)

    def test_changed_policy_rejected_on_audit(self):
        bundle = self.capture()
        changed = deepcopy(self.policy)
        changed["rustworld-world"]["commit_sha"] = "b" * 40
        with self.assertRaises(UntrustedReceipt):
            verify_pinned_source(self.jobs, changed, bundle)

    def test_missing_linux_nofollow_support_fails_closed(self):
        with patch.object(os, "O_NOFOLLOW", 0):
            with self.assertRaises(JobRejected):
                self.capture()
        self.assertEqual(self.jobs.audit("RustWorld", "source001")["state"],
                         "not_found_not_proof_of_nonexecution")

    def test_non_utf8_source_rejected_before_reservation(self):
        raw = b"\xff\xfe"
        self.source.write_bytes(raw)
        self.policy["rustworld-world"]["git_blob_sha1"] = blob_sha(raw)
        with self.assertRaises(JobRejected):
            self.capture()


if __name__ == "__main__":
    unittest.main()
