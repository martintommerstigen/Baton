"""R10 B5: local source/receipt/evidence lifecycle and negative controls."""
from __future__ import annotations

from contextlib import redirect_stdout, redirect_stderr
from copy import deepcopy
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from remote_security.pinned_source import capture_pinned_source
from remote_security.pinned_source_bundle import save_pinned_bundle, load_pinned_bundle
from remote_security.pinned_source_cli import main as cli_main
from remote_security.research_jobs import ResearchJobs, JobRejected, UntrustedReceipt


def git_blob(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\x00" + data).hexdigest()


class PinnedBundleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.base.chmod(0o700)
        self.root = self.base / "archive"
        self.source = self.root / "source/Dokumenter/kindergarden/src/world.rs"
        self.source.parent.mkdir(parents=True)
        self.raw = b"pub fn advance() { }\n"
        self.source.write_bytes(self.raw)
        self.policy = {"rustworld-world": {"path": "source/Dokumenter/kindergarden/src/world.rs",
                       "git_blob_sha1": git_blob(self.raw), "commit_sha": "a" * 40,
                       "branch": "RustWorld"}}
        self.key = b"X" * 32
        self.keyfile = self.base / "key"
        self.keyfile.write_bytes(self.key)
        self.keyfile.chmod(0o600)
        self.db = self.base / "jobs.db"
        self.artifact = self.base / "source.json"
        self.jobs = ResearchJobs(self.db, self.key, {"RustWorld": ["sha256-echo"]})

    def bundle(self):
        return capture_pinned_source(self.jobs, str(self.root), self.policy,
                                     "rustworld-world", "pinned0001")

    def test_capture_save_restart_audit_and_replay_refused(self):
        bundle = self.bundle()
        saved = save_pinned_bundle(self.jobs, self.policy, bundle, self.artifact)
        self.assertEqual(saved["state"], "private_pinned_bundle_saved_once")
        self.assertEqual(self.artifact.stat().st_mode & 0o777, 0o600)
        auditor = ResearchJobs(self.db, self.key, {"RustWorld": ["sha256-echo"]}, audit_only=True)
        checked = load_pinned_bundle(auditor, self.policy, self.artifact)
        self.assertEqual(checked["bundle"], bundle)
        self.assertEqual(checked["verification"]["state"], "verified_local_pinned_blob_only")
        self.assertEqual(saved["sha256"], checked["evidence_sha256"])
        with self.assertRaises(JobRejected):
            self.bundle()
        with self.assertRaises(FileExistsError):
            save_pinned_bundle(self.jobs, self.policy, bundle, self.artifact)

    def test_mutated_bundle_cannot_be_saved(self):
        bundle = self.bundle()
        bundle["source_text"] = "forged"
        with self.assertRaises(UntrustedReceipt):
            save_pinned_bundle(self.jobs, self.policy, bundle, self.artifact)
        self.assertFalse(self.artifact.exists())

    def test_tampered_evidence_rejected(self):
        save_pinned_bundle(self.jobs, self.policy, self.bundle(), self.artifact)
        self.artifact.write_bytes(self.artifact.read_bytes().replace(b"advance", b"advanceX"))
        with self.assertRaises(UntrustedReceipt):
            load_pinned_bundle(self.jobs, self.policy, self.artifact)

    def test_symlink_artifact_and_hardlink_rejected(self):
        bundle = self.bundle()
        other = self.base / "other"
        other.write_bytes(b"DO NOT OVERWRITE")
        self.artifact.symlink_to(other)
        with self.assertRaises((FileExistsError, OSError)):
            save_pinned_bundle(self.jobs, self.policy, bundle, self.artifact)
        self.assertEqual(other.read_bytes(), b"DO NOT OVERWRITE")
        self.artifact.unlink()
        save_pinned_bundle(self.jobs, self.policy, bundle, self.artifact)
        os.link(self.artifact, self.base / "alias")
        with self.assertRaises(PermissionError):
            load_pinned_bundle(self.jobs, self.policy, self.artifact)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "POSIX FIFO")
    def test_fifo_evidence_fails_without_blocking(self):
        os.mkfifo(self.artifact)
        with self.assertRaises(PermissionError):
            load_pinned_bundle(self.jobs, self.policy, self.artifact)

    def test_unsafe_parent_and_traversal_rejected(self):
        bundle = self.bundle()
        self.base.chmod(0o755)
        with self.assertRaises((ValueError, PermissionError)):
            save_pinned_bundle(self.jobs, self.policy, bundle, self.artifact)
        self.base.chmod(0o700)
        with self.assertRaises((ValueError, PermissionError)):
            save_pinned_bundle(self.jobs, self.policy, bundle, self.base / ".." / "bad.json")

    def test_fsync_failure_is_uncertain_no_overwrite(self):
        bundle = self.bundle()
        with patch("remote_security.pinned_source_bundle.os.fsync", side_effect=OSError("disk failure")):
            with self.assertRaises(OSError):
                save_pinned_bundle(self.jobs, self.policy, bundle, self.artifact)
        self.assertTrue(self.artifact.exists())
        with self.assertRaises(FileExistsError):
            save_pinned_bundle(self.jobs, self.policy, bundle, self.artifact)

    def test_policy_change_rejected_on_audit(self):
        save_pinned_bundle(self.jobs, self.policy, self.bundle(), self.artifact)
        changed = deepcopy(self.policy)
        changed["rustworld-world"]["commit_sha"] = "b" * 40
        with self.assertRaises(UntrustedReceipt):
            load_pinned_bundle(self.jobs, changed, self.artifact)

    def test_cli_capture_and_audit_only_print_hashes(self):
        from remote_security import pinned_source_cli as cli
        common = ["--database", str(self.db), "--receipt-key-file", str(self.keyfile),
                  "--evidence", str(self.artifact)]
        with patch.object(cli, "PINNED_POLICY", self.policy):
            output = io.StringIO()
            with redirect_stdout(output):
                status = cli_main(["capture", *common, "--source-root", str(self.root),
                                   "--source-id", "rustworld-world", "--job-id", "pinned0001"])
            self.assertEqual(status, 0)
            self.assertNotIn("pub fn", output.getvalue())
            self.assertEqual(json.loads(output.getvalue())["source_id"], "rustworld-world")
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(cli_main(["audit", *common, "--source-id", "rustworld-world"]), 0)
            self.assertEqual(json.loads(output.getvalue())["state"], "verified_local_pinned_blob_only")
            error = io.StringIO()
            with redirect_stderr(error):
                self.assertEqual(cli_main(["capture", *common, "--source-root", str(self.root),
                                           "--source-id", "rustworld-world", "--job-id", "pinned0001"]), 3)
            self.assertIn("rejected_or_uncertain_no_retry", error.getvalue())

    def test_cli_root_rejected_before_key_or_source(self):
        with patch("remote_security.pinned_source_cli.os.geteuid", return_value=0):
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                cli_main(["audit", "--database", str(self.db),
                          "--receipt-key-file", str(self.keyfile), "--evidence", str(self.artifact)])


if __name__ == "__main__":
    unittest.main()
