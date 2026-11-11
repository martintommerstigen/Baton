"""B5 R15 end-to-end *simulated peer UID* source RPC and durable audit.

Real Linux AF_UNIX transport and real pinned bytes/SQLite/HMAC are used.
Only the peer-UID method is injected, so this is NOT a distinct-UID or Greg
deployment claim; the separate root-only broker kernel test covers UID checks.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import socket
import tempfile
import threading
import unittest
from unittest.mock import patch

from remote_security.pinned_source import capture_pinned_source
from remote_security.pinned_source_bundle import save_pinned_bundle, load_pinned_bundle
from remote_security.research_jobs import ResearchJobs, JobRejected
from remote_security.source_broker import SourceBroker


@unittest.skipUnless(os.name == "posix" and os.geteuid() != 0
                     and hasattr(socket, "SO_PEERCRED"),
                     "non-root Linux Unix socket test")
class SourceBrokerPinnedE2E(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.base.chmod(0o700)
        self.socketdir = self.base / "socketdir"
        self.socketdir.mkdir(mode=0o710)
        self.socketpath = self.socketdir / "source.sock"
        self.evidence_dir = self.base / "evidence"
        self.evidence_dir.mkdir(mode=0o700)
        self.root = self.base / "archive"
        self.source = self.root / "source/Dokumenter/kindergarden/src/world.rs"
        self.source.parent.mkdir(parents=True)
        self.raw = b"pub fn step() { /* local test */ }\n"
        self.source.write_bytes(self.raw)
        blob = hashlib.sha1(b"blob " + str(len(self.raw)).encode() + b"\x00" + self.raw).hexdigest()
        self.policy = {"rustworld-world": {
            "path": "source/Dokumenter/kindergarden/src/world.rs",
            "git_blob_sha1": blob, "commit_sha": "a" * 40, "branch": "RustWorld",
        }}
        self.key = b"Z" * 32
        self.db = self.base / "receipts.db"
        self.allowed_uid = os.geteuid() + 1
        self.jobs = ResearchJobs(self.db, self.key, {"RustWorld": ["sha256-echo"]})
        self.broker = self.new_broker()
        self.broker.start()
        self.addCleanup(lambda: self.broker.close())

    def evidence(self, job_id):
        return self.evidence_dir / (job_id + ".json")

    def new_broker(self):
        def capture(source_id, job_id):
            bundle = capture_pinned_source(self.jobs, str(self.root), self.policy, source_id, job_id)
            saved = save_pinned_bundle(self.jobs, self.policy, bundle, self.evidence(job_id))
            return {"state": "completed_local_pinned_source", "source_id": source_id,
                    "job_id": job_id, "source_sha256": bundle["capture"]["content_sha256"],
                    "evidence_sha256": saved["sha256"]}

        def audit(source_id, job_id):
            auditor = ResearchJobs(self.db, self.key, {"RustWorld": ["sha256-echo"]}, audit_only=True)
            checked = load_pinned_bundle(auditor, self.policy, self.evidence(job_id))
            if checked["bundle"]["capture"]["source_id"] != source_id:
                raise ValueError("wrong source")
            return {"state": "verified_local_pinned_source", "source_id": source_id,
                    "job_id": job_id,
                    "source_sha256": checked["bundle"]["capture"]["content_sha256"],
                    "evidence_sha256": checked["evidence_sha256"]}

        return SourceBroker(str(self.socketpath), {self.allowed_uid},
                            set(self.policy), capture, audit)

    def exchange(self, action, job_id="source0001", source_id="rustworld-world"):
        raw = (json.dumps({"version": 1, "action": action, "source_id": source_id,
                           "job_id": job_id}, separators=(",", ":")) + "\n").encode()
        with patch.object(self.broker, "_peer_uid", return_value=self.allowed_uid):
            worker = threading.Thread(target=self.broker.accept_once, daemon=True)
            worker.start()
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                client.settimeout(5)
                client.connect(str(self.socketpath))
                client.sendall(raw)
                client.shutdown(socket.SHUT_WR)
                chunks = []
                while True:
                    chunk = client.recv(4096)
                    if not chunk:
                        break
                    chunks.append(chunk)
            worker.join(5)
            self.assertFalse(worker.is_alive(), "broker must finish one request")
        return json.loads(b"".join(chunks))

    def test_capture_restart_audit_and_replay_are_distinct(self):
        capture = self.exchange("capture")
        self.assertEqual(capture["state"], "completed_local_pinned_source")
        self.assertEqual(capture["source_sha256"], hashlib.sha256(self.raw).hexdigest())
        self.assertTrue(self.evidence("source0001").is_file())
        self.broker.close()
        self.broker = self.new_broker()
        self.broker.start()
        audit = self.exchange("audit")
        self.assertEqual(audit["state"], "verified_local_pinned_source")
        self.assertEqual(audit["source_sha256"], capture["source_sha256"])
        self.assertEqual(audit["evidence_sha256"], capture["evidence_sha256"])
        replay = self.exchange("capture")
        self.assertEqual(replay["state"], "rejected_or_uncertain_no_retry")
        self.assertEqual(self.exchange("audit")["state"], "verified_local_pinned_source")

    def test_evidence_tampering_rejected_after_restart(self):
        self.assertEqual(self.exchange("capture")["state"], "completed_local_pinned_source")
        evidence = self.evidence("source0001")
        evidence.write_bytes(evidence.read_bytes().replace(b"step", b"STOP"))
        self.broker.close()
        self.broker = self.new_broker()
        self.broker.start()
        self.assertEqual(self.exchange("audit")["state"], "rejected_or_uncertain_no_retry")
        self.assertEqual(self.exchange("capture")["state"], "rejected_or_uncertain_no_retry")


if __name__ == "__main__":
    unittest.main()
