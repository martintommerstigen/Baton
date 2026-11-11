"""B5 R16: real two-UID AF_UNIX -> source bytes -> receipt -> restart audit.

Root is used only by the trusted-push CI harness to fork two *unprivileged*
process identities. Neither the broker nor the client runs as root.
All source bytes and HMAC keys are disposable synthetic fixtures, not Greg data.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import select
import signal
import socket
import tempfile
import unittest

from remote_security.pinned_source import capture_pinned_source
from remote_security.pinned_source_bundle import save_pinned_bundle, load_pinned_bundle
from remote_security.research_jobs import ResearchJobs
from remote_security.source_broker import SourceBroker


SERVICE_UID = 21001
CLIENT_UID = 21003
DENIED_UID = 21004
SHARED_GID = 21002


@unittest.skipUnless(os.name == "posix" and os.geteuid() == 0
                     and hasattr(os, "fork") and hasattr(socket, "SO_PEERCRED"),
                     "trusted root-only two-UID Linux kernel test")
class CrossUidPinnedSourceE2E(unittest.TestCase):
    def _ready(self, fd):
        readable, _, _ = select.select([fd], [], [], 8)
        self.assertTrue(readable, "unprivileged broker did not become ready")
        status = os.read(fd, 1)
        if status != b"R":
            detail = os.read(fd, 128) if status == b"E" else b""
            self.fail("unprivileged child setup failed: " + repr(status + detail))

    def _client(self, uid, path, action):
        read_fd, write_fd = os.pipe()
        pid = os.fork()
        if pid == 0:
            try:
                os.close(read_fd)
                os.setgid(SHARED_GID)
                os.setuid(uid)
                request = (json.dumps({"version": 1, "action": action,
                                       "source_id": "rustworld-world",
                                       "job_id": "source0001"},
                                      separators=(",", ":")) + "\n").encode()
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                    sock.settimeout(5)
                    sock.connect(str(path))
                    try:
                        sock.sendall(request)
                        sock.shutdown(socket.SHUT_WR)
                        parts = []
                        while True:
                            part = sock.recv(4096)
                            if not part:
                                break
                            parts.append(part)
                        result = b"".join(parts)
                    except (ConnectionResetError, BrokenPipeError):
                        result = b""
                os.write(write_fd, result)
                os._exit(0)
            except BaseException as exc:
                os.write(write_fd, ("ERROR:" + type(exc).__name__).encode())
                os._exit(3)
        os.close(write_fd)
        parts = []
        while True:
            part = os.read(read_fd, 4096)
            if not part:
                break
            parts.append(part)
        os.close(read_fd)
        _, status = os.waitpid(pid, 0)
        self.assertEqual(os.waitstatus_to_exitcode(status), 0)
        result = b"".join(parts)
        self.assertFalse(result.startswith(b"ERROR:"), result)
        return result

    def test_real_uid_capture_restart_audit_replay_and_forged_uid(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            base.chmod(0o755)  # only traversal, never write by client
            archive = base / "archive"
            source = archive / "source/Dokumenter/kindergarden/src/world.rs"
            source.parent.mkdir(parents=True, mode=0o755)
            raw = b"pub fn step() { /* disposable kernel test */ }\n"
            source.write_bytes(raw)
            source.chmod(0o644)
            blob = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
            policy = {"rustworld-world": {
                "path": "source/Dokumenter/kindergarden/src/world.rs",
                "git_blob_sha1": blob, "commit_sha": "a" * 40, "branch": "RustWorld"}}
            socketdir = base / "socketdir"
            socketdir.mkdir(mode=0o710)
            os.chown(socketdir, SERVICE_UID, SHARED_GID)
            socketdir.chmod(0o710)
            path = socketdir / "source.sock"
            private = base / "private"
            private.mkdir(mode=0o700)
            os.chown(private, SERVICE_UID, SHARED_GID)
            private.chmod(0o700)
            db = private / "receipts.db"
            evidence = private / "source0001.json"
            key = b"R16-LOCAL-TEST-KEY-NOT-A-SECRET!!"  # 33 synthetic bytes
            ready_r, ready_w = os.pipe()
            pid = os.fork()
            if pid == 0:
                phase = "drop"
                try:
                    os.close(ready_r)
                    os.setgid(SHARED_GID)
                    os.setuid(SERVICE_UID)
                    phase = "jobs"
                    jobs = ResearchJobs(db, key, {"RustWorld": ["sha256-echo"]})

                    def capture(source_id, job_id):
                        bundle = capture_pinned_source(jobs, str(archive), policy, source_id, job_id)
                        saved = save_pinned_bundle(jobs, policy, bundle, evidence)
                        return {"state": "completed_local_pinned_source",
                                "source_id": source_id, "job_id": job_id,
                                "source_sha256": bundle["capture"]["content_sha256"],
                                "evidence_sha256": saved["sha256"]}

                    def audit(source_id, job_id):
                        auditor = ResearchJobs(db, key, {"RustWorld": ["sha256-echo"]},
                                               audit_only=True)
                        checked = load_pinned_bundle(auditor, policy, evidence)
                        if (checked["bundle"]["capture"]["source_id"] != source_id
                                or checked["bundle"]["job"]["receipt"]["job_id"] != job_id):
                            raise ValueError("audit mismatch")
                        return {"state": "verified_local_pinned_source",
                                "source_id": source_id, "job_id": job_id,
                                "source_sha256": checked["bundle"]["capture"]["content_sha256"],
                                "evidence_sha256": checked["evidence_sha256"]}

                    phase = "broker-start"
                    broker = SourceBroker(str(path), {CLIENT_UID},
                                          set(policy), capture, audit)
                    broker.start()
                    os.write(ready_w, b"R")
                    broker.accept_once()  # wrong UID, must not read bytes
                    broker.accept_once()  # permitted capture
                    broker.close()
                    broker = SourceBroker(str(path), {CLIENT_UID},
                                          set(policy), capture, audit)
                    broker.start()
                    os.write(ready_w, b"R")
                    broker.accept_once()  # permitted audit after restart
                    broker.accept_once()  # replay capture rejected
                    broker.close()
                    os._exit(0)
                except BaseException as exc:
                    # Failure-only diagnostic: exception class and errno, never
                    # private paths, source text, keys or message contents.
                    detail = (phase + ":" + type(exc).__name__ + ":" +
                              str(getattr(exc, "errno", ""))).encode("ascii", "replace")
                    try:
                        os.write(ready_w, b"E" + detail[:100])
                    except OSError:
                        pass
                    os._exit(3)
            os.close(ready_w)
            try:
                self._ready(ready_r)
                self.assertEqual(self._client(DENIED_UID, path, "capture"), b"")
                capture = json.loads(self._client(CLIENT_UID, path, "capture"))
                self.assertEqual(capture["state"], "completed_local_pinned_source")
                self.assertEqual(capture["source_sha256"], hashlib.sha256(raw).hexdigest())
                self._ready(ready_r)
                audit = json.loads(self._client(CLIENT_UID, path, "audit"))
                self.assertEqual(audit["state"], "verified_local_pinned_source")
                self.assertEqual(audit["source_sha256"], capture["source_sha256"])
                self.assertEqual(audit["evidence_sha256"], capture["evidence_sha256"])
                replay = json.loads(self._client(CLIENT_UID, path, "capture"))
                self.assertEqual(replay["state"], "rejected_or_uncertain_no_retry")
                _, status = os.waitpid(pid, 0)
                pid = None
                self.assertEqual(os.waitstatus_to_exitcode(status), 0)
                self.assertTrue(evidence.is_file())
                self.assertEqual(evidence.stat().st_uid, SERVICE_UID)
                self.assertEqual(evidence.stat().st_mode & 0o777, 0o600)
            finally:
                os.close(ready_r)
                if pid is not None:
                    os.kill(pid, signal.SIGKILL)
                    os.waitpid(pid, 0)


if __name__ == "__main__":
    unittest.main()
