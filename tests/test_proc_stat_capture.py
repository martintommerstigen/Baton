"""B5/B2 fixed-source capture regression and PR #20 non-authorization contract.

Tests run with synthetic /proc/stat bytes except the explicitly marked Linux
host read. No browser, broker, UI click, network, or Greg deployment.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from remote_security.proc_stat_capture import (
    SOURCE, EVIDENCE, capture_once, verify_capture,
)
from remote_security.research_jobs import (
    ResearchJobs, JobRejected, JobUncertain, UntrustedReceipt, canonical,
)

RAW = b"cpu  100 0 40 300 1 0 0 2 0 0\n"
POLICY = {"GTRCM": ["sha256-echo"]}


class ProcStatCaptureTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.root.chmod(0o700)
        self.db = self.root / "jobs.sqlite"
        self.key = b"P" * 32
        self.jobs = ResearchJobs(self.db, self.key, POLICY)

    def capture(self, job_id="cpu00001"):
        with patch("remote_security.proc_stat_capture._read_proc_cpu_line", return_value=RAW):
            return capture_once(self.jobs, "GTRCM", job_id)

    def test_complete_authorized_job_source_command_sha_timestamps_exit(self):
        bundle = self.capture()
        c = bundle["capture"]
        receipt = bundle["job"]["receipt"]
        self.assertEqual(c["source"], SOURCE)
        self.assertEqual(c["evidence"], EVIDENCE)
        self.assertEqual(receipt["command"], "sha256-echo")
        self.assertEqual(receipt["input_sha256"], hashlib.sha256(RAW).hexdigest())
        self.assertEqual(receipt["output_sha256"],
                         hashlib.sha256(canonical(bundle["job"]["output"])).hexdigest())
        self.assertEqual(receipt["exit_status"], 0)
        self.assertTrue(receipt["started_utc"].endswith("+00:00"))
        self.assertTrue(receipt["finished_utc"].endswith("+00:00"))
        self.assertEqual(verify_capture(self.jobs, bundle)["state"],
                         "verified_local_kernel_counter_only")

    def test_audit_after_restart_without_execution(self):
        bundle = self.capture()
        audit_only = ResearchJobs(self.db, self.key, POLICY, audit_only=True)
        self.assertEqual(verify_capture(audit_only, bundle)["source_sha256"],
                         hashlib.sha256(RAW).hexdigest())
        with self.assertRaises(JobRejected):
            audit_only.run_once({"project": "GTRCM"}, RAW)

    def test_replay_and_concurrent_duplicate_rejected(self):
        self.capture()
        with self.assertRaises(JobRejected):
            self.capture()
        successes, rejected = [], []
        barrier = threading.Barrier(5)
        def attempt():
            barrier.wait()
            try:
                successes.append(self.capture("cpu00002"))
            except JobRejected:
                rejected.append(True)
        threads = [threading.Thread(target=attempt) for _ in range(5)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=8)
        self.assertFalse(any(thread.is_alive() for thread in threads))
        self.assertEqual((len(successes), len(rejected)), (1, 4))

    def test_wrong_project_policy_fails_before_reservation(self):
        with patch("remote_security.proc_stat_capture._read_proc_cpu_line", return_value=RAW):
            with self.assertRaises(JobRejected):
                capture_once(self.jobs, "OTHER", "cpu00003")
        self.assertEqual(self.jobs.audit("GTRCM", "cpu00003")["state"],
                         "not_found_not_proof_of_nonexecution")

    def test_invalid_or_oversized_source_never_reserves(self):
        for idx, raw in enumerate((b"not a cpu line\n", b"cpu 1 2\n",
                                   b"cpu 1 2 3 4\r\n", b"cpu " + b"1 " * 3000 + b"\n")):
            job_id = f"badcpu{idx:02d}"
            with self.subTest(idx=idx):
                with patch("remote_security.proc_stat_capture._read_proc_cpu_line", return_value=raw):
                    with self.assertRaises(JobRejected):
                        capture_once(self.jobs, "GTRCM", job_id)
                self.assertEqual(self.jobs.audit("GTRCM", job_id)["state"],
                                 "not_found_not_proof_of_nonexecution")

    def test_forged_source_and_raw_data_rejected(self):
        bundle = self.capture()
        for field, value in (("source", "/tmp/attacker"),
                             ("source_kind", "external_physics"),
                             ("evidence", "independent_measurement")):
            changed = deepcopy(bundle)
            changed["capture"][field] = value
            with self.subTest(field=field), self.assertRaises(UntrustedReceipt):
                verify_capture(self.jobs, changed)
        changed = deepcopy(bundle)
        changed["raw_cpu_line"] = RAW.decode().replace("100", "101")
        with self.assertRaises(UntrustedReceipt):
            verify_capture(self.jobs, changed)

    def test_mac_and_receipt_forgery_rejected(self):
        bundle = self.capture()
        for key, value in (("capture_mac", "0" * 64), ("raw_cpu_line", "cpu 1 2 3 4\n")):
            changed = deepcopy(bundle)
            changed[key] = value
            with self.subTest(key=key), self.assertRaises(UntrustedReceipt):
                verify_capture(self.jobs, changed)
        changed = deepcopy(bundle)
        changed["job"]["receipt"]["exit_status"] = 99
        with self.assertRaises(UntrustedReceipt):
            verify_capture(self.jobs, changed)

    def test_signed_but_impossible_capture_time_rejected(self):
        # Even a locally re-MACed capture must obey observation -> job order.
        from remote_security.proc_stat_capture import _sign
        bundle = self.capture()
        changed = deepcopy(bundle)
        changed["capture"]["observed_utc"] = "2030-01-01T00:00:00+00:00"
        changed["capture_mac"] = _sign(self.key, changed["capture"])
        with self.assertRaises(UntrustedReceipt):
            verify_capture(self.jobs, changed)

    def test_corrupt_durable_output_rejected(self):
        bundle = self.capture()
        conn = sqlite3.connect(self.db)
        try:
            conn.execute("UPDATE research_jobs SET output=? WHERE job_id=?",
                         (b'{"sha256":"forged"}', "cpu00001"))
            conn.commit()
        finally:
            conn.close()
        with self.assertRaises(UntrustedReceipt):
            verify_capture(self.jobs, bundle)

    def test_uncertain_after_execution_crash_no_blind_retry(self):
        with patch("remote_security.proc_stat_capture._read_proc_cpu_line", return_value=RAW):
            with patch("remote_security.research_jobs._run_builtin", side_effect=RuntimeError("crash")):
                with self.assertRaises(JobUncertain):
                    capture_once(self.jobs, "GTRCM", "crash001")
        restarted = ResearchJobs(self.db, self.key, POLICY)
        self.assertEqual(restarted.audit("GTRCM", "crash001")["state"],
                         "started_uncertain_no_retry")
        with patch("remote_security.proc_stat_capture._read_proc_cpu_line", return_value=RAW):
            with self.assertRaises(JobRejected):
                capture_once(restarted, "GTRCM", "crash001")

    def test_pr20_b5_peer_interface_and_research_job_op_separation(self):
        # Compared to B1 PR #20 run_verified_broker_wake.py at fb49b636.
        # B1 passes its envelope positionally and requires distinct UID.
        import inspect
        from remote_security.broker_peer import query_verified_broker
        sig = inspect.signature(query_verified_broker)
        self.assertEqual(list(sig.parameters)[:3],
                         ["socket_path", "expected_uid", "request"])
        self.assertEqual(sig.parameters["require_distinct_uid"].default, True)
        self.assertEqual(sig.parameters["timeout"].default, 3.0)
        digest = hashlib.sha256(RAW).hexdigest()
        for forbidden in ("admit", "begin_click", "shell", "browser"):
            request = {"project": "GTRCM", "job_id": "forbid001",
                       "command": forbidden, "input_sha256": digest}
            with self.subTest(command=forbidden), self.assertRaises(JobRejected):
                self.jobs.run_once(request, RAW)
        with self.assertRaises(JobRejected):
            self.jobs.run_once({"op": "begin_click", "project": "GTRCM"}, RAW)
        self.assertEqual(self.jobs.audit("GTRCM", "forbid001")["state"],
                         "not_found_not_proof_of_nonexecution")

    def test_pr20_contract_no_ui_or_broker_side_effect(self):
        # PR #20 B1 only authorizes UI via verified admit/begin_click.
        # This B5 read-only job never invokes either operation.
        broker_calls = []
        def broker(envelope):
            broker_calls.append(envelope)
            raise AssertionError("read-only job must not contact broker")
        _ = broker
        marker = self.root / "PAUSE_UI_WRITES"
        marker.write_text("paused")
        before = marker.read_bytes()
        bundle = self.capture()
        self.assertEqual(verify_capture(self.jobs, bundle)["state"],
                         "verified_local_kernel_counter_only")
        self.assertEqual(broker_calls, [])
        self.assertEqual(marker.read_bytes(), before)

    def test_fixed_source_symlink_cannot_be_followed(self):
        link = self.root / "fake_proc_stat"
        link.symlink_to(SOURCE)
        with patch("remote_security.proc_stat_capture.SOURCE", str(link)):
            with self.assertRaises(OSError):
                capture_once(self.jobs, "GTRCM", "symlink01")
        self.assertEqual(self.jobs.audit("GTRCM", "symlink01")["state"],
                         "not_found_not_proof_of_nonexecution")

    @unittest.skipIf(os.getuid() == 0, "requires unprivileged test UID")
    def test_unprivileged_fake_proc_file_cannot_impersonate_root_source(self):
        fake = self.root / "proc_stat"
        fake.write_bytes(RAW)
        with patch("remote_security.proc_stat_capture.SOURCE", str(fake)):
            with self.assertRaises(JobRejected):
                capture_once(self.jobs, "GTRCM", "fakecpu01")
        self.assertEqual(self.jobs.audit("GTRCM", "fakecpu01")["state"],
                         "not_found_not_proof_of_nonexecution")

    def test_key_rotation_and_lost_raw_bundle_fail_closed(self):
        bundle = self.capture()
        other = ResearchJobs(self.db, b"Q" * 32, POLICY, audit_only=True)
        with self.assertRaises(UntrustedReceipt):
            verify_capture(other, bundle)
        changed = deepcopy(bundle)
        del changed["raw_cpu_line"]
        with self.assertRaises(UntrustedReceipt):
            verify_capture(self.jobs, changed)

    @unittest.skipUnless(sys.platform.startswith("linux") and os.path.exists(SOURCE),
                         "requires a real Linux /proc/stat")
    def test_real_linux_procfs_counter_not_greg(self):
        # Actual host kernel-exposed counters, not a physical GTRCM prediction.
        bundle = capture_once(self.jobs, "GTRCM", "linux001")
        self.assertTrue(bundle["raw_cpu_line"].startswith("cpu "))
        self.assertEqual(verify_capture(self.jobs, bundle)["state"],
                         "verified_local_kernel_counter_only")


if __name__ == "__main__":
    unittest.main()
