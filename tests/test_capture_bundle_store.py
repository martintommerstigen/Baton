"""B5 private capture persistence: actual raw data, no overwrite or replay."""
from __future__ import annotations

from copy import deepcopy
import os
from pathlib import Path
import sqlite3
import stat
import tempfile
import unittest
from unittest.mock import patch

from remote_security.capture_bundle_store import (
    MAX_BUNDLE, save_verified_capture, load_verified_capture,
)
from remote_security.proc_stat_capture import capture_once
from remote_security.research_jobs import ResearchJobs, UntrustedReceipt

RAW = b"cpu  100 0 40 300 1 0 0 2 0 0\n"
POLICY = {"GTRCM": ["sha256-echo"]}


class CaptureBundleStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.root.chmod(0o700)
        self.db = self.root / "jobs.db"
        self.key = b"S" * 32
        self.jobs = ResearchJobs(self.db, self.key, POLICY)
        with patch("remote_security.proc_stat_capture._read_proc_cpu_line", return_value=RAW):
            self.bundle = capture_once(self.jobs, "GTRCM", "bundle001")
        self.artifact = self.root / "raw-cpu.json"

    def test_raw_bundle_saved_exclusively_and_reverified_after_restart(self):
        saved = save_verified_capture(self.jobs, self.bundle, self.artifact)
        self.assertEqual(saved["state"], "private_capture_saved_once")
        self.assertEqual(saved["bytes"], self.artifact.stat().st_size)
        self.assertEqual(self.artifact.stat().st_mode & 0o777, 0o600)
        restarted = ResearchJobs(self.db, self.key, POLICY, audit_only=True)
        restored = load_verified_capture(restarted, self.artifact)
        self.assertEqual(restored["raw_cpu_line"].encode("ascii"), RAW)
        self.assertEqual(restored, self.bundle)
        self.assertEqual(len(saved["sha256"]), 64)

    def test_existing_artifact_cannot_be_overwritten(self):
        self.artifact.write_text("existing")
        with self.assertRaises(FileExistsError):
            save_verified_capture(self.jobs, self.bundle, self.artifact)
        self.assertEqual(self.artifact.read_text(), "existing")

    def test_symlink_and_path_traversal_rejected(self):
        target = self.root / "target"
        target.write_text("protected")
        self.artifact.symlink_to(target)
        with self.assertRaises((FileExistsError, OSError, ValueError)):
            save_verified_capture(self.jobs, self.bundle, self.artifact)
        self.assertEqual(target.read_text(), "protected")
        with self.assertRaises((OSError, ValueError)):
            save_verified_capture(self.jobs, self.bundle, self.root / ".." / "bad.json")

    def test_permissive_parent_rejected(self):
        self.root.chmod(0o755)
        with self.assertRaises((ValueError, PermissionError)):
            save_verified_capture(self.jobs, self.bundle, self.artifact)

    def test_tampered_raw_artifact_rejected(self):
        save_verified_capture(self.jobs, self.bundle, self.artifact)
        data = self.artifact.read_bytes().replace(b"cpu  100", b"cpu  101")
        self.artifact.write_bytes(data)
        with self.assertRaises(UntrustedReceipt):
            load_verified_capture(self.jobs, self.artifact)

    def test_hardlinked_artifact_rejected_on_load(self):
        save_verified_capture(self.jobs, self.bundle, self.artifact)
        alias = self.root / "hardlink.json"
        os.link(self.artifact, alias)
        with self.assertRaises(PermissionError):
            load_verified_capture(self.jobs, self.artifact)

    def test_symlink_artifact_rejected_on_load(self):
        save_verified_capture(self.jobs, self.bundle, self.artifact)
        alias = self.root / "alias.json"
        alias.symlink_to(self.artifact)
        with self.assertRaises((OSError, ValueError)):
            load_verified_capture(self.jobs, alias)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "requires POSIX FIFO")
    def test_fifo_artifact_rejected_without_blocking(self):
        os.mkfifo(self.artifact, 0o600)
        with self.assertRaises(PermissionError):
            load_verified_capture(self.jobs, self.artifact)

    def test_permissive_artifact_rejected(self):
        save_verified_capture(self.jobs, self.bundle, self.artifact)
        self.artifact.chmod(0o644)
        with self.assertRaises(PermissionError):
            load_verified_capture(self.jobs, self.artifact)

    def test_oversized_and_noncanonical_artifact_rejected(self):
        self.artifact.write_bytes(b"x" * (MAX_BUNDLE + 1))
        self.artifact.chmod(0o600)
        with self.assertRaises(UntrustedReceipt):
            load_verified_capture(self.jobs, self.artifact)
        self.artifact.write_bytes(b'{"raw_cpu_line": "not canonical"}\n')
        with self.assertRaises(UntrustedReceipt):
            load_verified_capture(self.jobs, self.artifact)

    def test_database_tampering_blocks_export(self):
        db = sqlite3.connect(self.db)
        try:
            db.execute("UPDATE research_jobs SET input_sha=? WHERE job_id=?",
                       ("0" * 64, "bundle001"))
            db.commit()
        finally:
            db.close()
        with self.assertRaises(UntrustedReceipt):
            save_verified_capture(self.jobs, self.bundle, self.artifact)
        self.assertFalse(self.artifact.exists())

    def test_fsync_failure_is_uncertain_and_never_overwritten(self):
        with patch("remote_security.capture_bundle_store.os.fsync",
                   side_effect=OSError("injected fsync failure")):
            with self.assertRaises(OSError):
                save_verified_capture(self.jobs, self.bundle, self.artifact)
        # File may exist, but failed fsync is not durable-success evidence.
        self.assertTrue(self.artifact.exists())
        with self.assertRaises(FileExistsError):
            save_verified_capture(self.jobs, self.bundle, self.artifact)
        self.assertEqual(self.jobs.audit("GTRCM", "bundle001")["state"],
                         "completed_local_only")

    def test_missing_artifact_is_not_proof_of_no_measurement(self):
        with self.assertRaises(FileNotFoundError):
            load_verified_capture(self.jobs, self.artifact)
        self.assertEqual(self.jobs.audit("GTRCM", "bundle001")["state"],
                         "completed_local_only")


if __name__ == "__main__":
    unittest.main()
