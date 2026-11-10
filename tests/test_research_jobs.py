"""B5/B2 isolated negative tests. No network, UI, shell or Greg calls."""
from datetime import datetime, timezone
import hashlib
import hmac
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch

from remote_security.research_jobs import (ResearchJobs, JobRejected, JobUncertain,
                                           UntrustedReceipt, canonical, _load_receipt_key)


class ResearchJobsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.root.chmod(0o700)
        self.db = self.root / "jobs.db"
        self.key = b"R" * 32
        self.allowed = {"GTRCM_TEST": ["sha256-echo", "json-object-check", "utf8-line-count"]}
        self.jobs = ResearchJobs(self.db, self.key, self.allowed,
                                 clock=lambda: datetime(2026, 11, 10, tzinfo=timezone.utc))

    def request(self, payload=b"hello", command="sha256-echo", job_id="job00001", project="GTRCM_TEST"):
        return {"project": project, "job_id": job_id, "command": command,
                "input_sha256": hashlib.sha256(payload).hexdigest()}

    def test_success_signed_durable_audit_and_restart(self):
        payload = b"abc\n"
        r = self.jobs.run_once(self.request(payload), payload)
        self.assertEqual(r["receipt"]["exit_status"], 0)
        self.assertEqual(r["receipt"]["input_sha256"], hashlib.sha256(payload).hexdigest())
        self.assertEqual(r["receipt"]["output_sha256"], hashlib.sha256(canonical(r["output"])).hexdigest())
        self.assertEqual(r["mac"], hmac.new(self.key, canonical(r["receipt"]), hashlib.sha256).hexdigest())
        restarted = ResearchJobs(self.db, self.key, self.allowed)
        self.assertEqual(restarted.audit("GTRCM_TEST", "job00001")["receipt"], r["receipt"])
        with self.assertRaises(JobRejected):
            restarted.run_once(self.request(payload), payload)

    def test_wrong_digest_does_not_reserve(self):
        req = self.request()
        req["input_sha256"] = "0" * 64
        with self.assertRaises(JobRejected):
            self.jobs.run_once(req, b"hello")
        self.assertEqual(self.jobs.audit("GTRCM_TEST", "job00001")["state"], "not_found_not_proof_of_nonexecution")

    def test_wrong_project_and_command_rejected(self):
        for req in (self.request(project="OTHER_TEST"), self.request(command="shell-exec")):
            with self.assertRaises(JobRejected):
                self.jobs.run_once(req, b"hello")

    def test_no_arbitrary_paths_or_argv_in_schema(self):
        req = self.request()
        req["path"] = "/etc/shadow"
        with self.assertRaises(JobRejected):
            self.jobs.run_once(req, b"hello")

    def test_malformed_input_size_and_identifiers(self):
        for payload in ("not bytes", b"a" * 65537):
            with self.assertRaises(JobRejected):
                self.jobs.run_once(self.request(), payload)
        with self.assertRaises(JobRejected):
            self.jobs.run_once(self.request(job_id="../evil"), b"hello")

    def test_duplicate_json_and_nonfinite_are_failed_checks_not_exceptions(self):
        for n, data in enumerate((b'{"a":1,"a":2}', b'{"a":NaN}', b'[]', b'not json')):
            result = self.jobs.run_once(self.request(data, "json-object-check", f"invalid{n:02}"), data)
            self.assertEqual(result["receipt"]["exit_status"], 2)
            self.assertEqual(result["output"], {"error": "invalid_json_object"})

    def test_valid_json_no_sensitive_field_names_in_output(self):
        data = b'{"private_token":"secret","other":2}'
        result = self.jobs.run_once(self.request(data, "json-object-check"), data)
        self.assertEqual(result["output"], {"valid": True, "top_level_fields": 2})
        self.assertNotIn("private_token", json.dumps(result))
        self.assertNotIn("secret", json.dumps(result))

    def test_utf8_lines_and_invalid_utf8(self):
        for job, data, expected in (("lines000", b"one\ntwo", {"lines": 2, "bytes": 7}),
                                    ("lines001", b"", {"lines": 0, "bytes": 0})):
            result = self.jobs.run_once(self.request(data, "utf8-line-count", job), data)
            self.assertEqual(result["output"], expected)
        data = b"\xff"
        result = self.jobs.run_once(self.request(data, "utf8-line-count", "lines002"), data)
        self.assertEqual(result["receipt"]["exit_status"], 2)

    def test_concurrent_duplicate_only_one_reserved(self):
        successes, failures = [], []
        barrier = threading.Barrier(6)
        def worker():
            barrier.wait()
            try:
                successes.append(self.jobs.run_once(self.request(), b"hello"))
            except JobRejected as exc:
                failures.append(str(exc))
        threads = [threading.Thread(target=worker) for _ in range(6)]
        for t in threads: t.start()
        for t in threads: t.join(5)
        self.assertEqual(len(successes), 1)
        self.assertEqual(len(failures), 5)

    def test_crash_after_reservation_stays_uncertain_after_restart(self):
        with patch("remote_security.research_jobs._run_builtin", side_effect=RuntimeError("simulated crash")):
            with self.assertRaises(JobUncertain):
                self.jobs.run_once(self.request(), b"hello")
        restarted = ResearchJobs(self.db, self.key, self.allowed)
        self.assertEqual(restarted.audit("GTRCM_TEST", "job00001"), {"state": "started_uncertain_no_retry"})
        with self.assertRaises(JobRejected):
            restarted.run_once(self.request(), b"hello")

    def test_forged_receipt_or_output_rejected(self):
        self.jobs.run_once(self.request(), b"hello")
        db = sqlite3.connect(self.db)
        try:
            db.execute("UPDATE research_jobs SET output=? WHERE job_id=?", (b'{"sha256":"forged"}', "job00001"))
            db.commit()
        finally:
            db.close()
        with self.assertRaises(UntrustedReceipt):
            self.jobs.audit("GTRCM_TEST", "job00001")

    def test_policy_rotation_does_not_silently_verify_old_receipt(self):
        self.jobs.run_once(self.request(), b"hello")
        other = ResearchJobs(self.db, self.key, {"GTRCM_TEST": ["sha256-echo"]})
        with self.assertRaises(UntrustedReceipt):
            other.audit("GTRCM_TEST", "job00001")

    def test_key_rotation_does_not_silently_verify_old_receipt(self):
        self.jobs.run_once(self.request(), b"hello")
        other = ResearchJobs(self.db, b"S" * 32, self.allowed)
        with self.assertRaises(UntrustedReceipt):
            other.audit("GTRCM_TEST", "job00001")

    def test_symlink_db_rejected(self):
        link = self.root / "link.db"
        link.symlink_to(self.db)
        with self.assertRaises((OSError, ValueError)):
            ResearchJobs(link, self.key, self.allowed)

    def test_key_file_symlink_and_world_readable_rejected(self):
        path = self.root / "key"
        path.write_bytes(self.key)
        path.chmod(0o600)
        self.assertEqual(_load_receipt_key(path), self.key)
        link = self.root / "link"
        link.symlink_to(path)
        with self.assertRaises((OSError, ValueError, PermissionError)):
            _load_receipt_key(link)
        path.chmod(0o644)
        with self.assertRaises((OSError, ValueError, PermissionError)):
            _load_receipt_key(path)

    def test_db_command_or_input_tampering_rejected(self):
        self.jobs.run_once(self.request(), b"hello")
        db = sqlite3.connect(self.db)
        try:
            db.execute("UPDATE research_jobs SET input_sha=? WHERE job_id=?", ("0" * 64, "job00001"))
            db.commit()
        finally:
            db.close()
        with self.assertRaises(UntrustedReceipt):
            self.jobs.audit("GTRCM_TEST", "job00001")

    def test_short_real_project_name_allowed(self):
        obj = ResearchJobs(self.root / "other.db", self.key, {"GTRCM": ["sha256-echo"]})
        req = self.request(project="GTRCM")
        self.assertEqual(obj.run_once(req, b"hello")["receipt"]["project"], "GTRCM")

    def test_audit_not_found_is_not_delivery_proof(self):
        self.assertEqual(self.jobs.audit("GTRCM_TEST", "missing00"),
                         {"state": "not_found_not_proof_of_nonexecution"})


if __name__ == "__main__":
    unittest.main()
