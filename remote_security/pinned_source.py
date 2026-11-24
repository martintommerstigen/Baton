"""B5/R9: read an explicitly pinned RustWorld source blob, never a shell or UI.

The operator supplies a fixed source-id allowlist; remote callers can only select
one of its IDs. A matching Git blob SHA-1 authenticates bytes against the pinned
blob reference, not the claimed Git commit, checkout, machine, or author.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import hmac
import os
from pathlib import Path
import re
import stat

from remote_security.research_jobs import (
    JobRejected, ResearchJobs, UntrustedReceipt, canonical,
)

MAX_SOURCE = 32768
DOMAIN = b"baton.pinned_source.v1\x00"
HEX40 = re.compile(r"[0-9a-f]{40}\Z")
ID = re.compile(r"[a-z][a-z0-9_-]{2,63}\Z")
BRANCH = "RustWorld"
REPO = "martintommerstigen/GTRCM"
EVIDENCE = "local_bytes_match_pinned_blob_not_commit_or_host_attestation"
DIR_FLAGS = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
FILE_FLAGS = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NONBLOCK", 0)


def _path_parts(value, absolute=False):
    if type(value) is not str or not value or "\x00" in value:
        raise JobRejected("invalid source path")
    if absolute != value.startswith("/"):
        raise JobRejected("source path absolute/relative mismatch")
    parts = value.split("/")[1:] if absolute else value.split("/")
    if not parts or any(part in ("", ".", "..") for part in parts):
        raise JobRejected("source path traversal or normalization forbidden")
    return parts


def _policy_entry(entry):
    if type(entry) is not dict or set(entry) != {"path", "git_blob_sha1", "commit_sha", "branch"}:
        raise JobRejected("exact pinned source policy required")
    parts = _path_parts(entry["path"])
    if (not entry["path"].startswith("source/Dokumenter/")
            and entry["path"] != "source/protocol.rs"):
        raise JobRejected("RustWorld source subtree only")
    if len(parts) < 2 or len(parts) > 20 or len(entry["path"]) > 300:
        raise JobRejected("invalid pinned path length")
    if (entry["branch"] != BRANCH or type(entry["commit_sha"]) is not str
            or HEX40.fullmatch(entry["commit_sha"]) is None
            or type(entry["git_blob_sha1"]) is not str
            or HEX40.fullmatch(entry["git_blob_sha1"]) is None):
        raise JobRejected("invalid immutable Git provenance")
    return dict(entry)


def _dir_ok(fd):
    s = os.fstat(fd)
    if not stat.S_ISDIR(s.st_mode) or s.st_uid not in (0, os.getuid()):
        raise JobRejected("unsafe source directory ownership")
    if s.st_mode & 0o022 and not (s.st_uid == 0 and s.st_mode & stat.S_ISVTX):
        raise JobRejected("writable source directory")


def _open_dir(parent_fd, name):
    fd = os.open(name, DIR_FLAGS, dir_fd=parent_fd)
    try:
        _dir_ok(fd)
        return fd
    except BaseException:
        os.close(fd)
        raise


def _read_pinned(root, entry):
    """Walk every directory via dirfd/O_NOFOLLOW; never trust resolved paths."""
    if os.geteuid() == 0:
        raise JobRejected("root source inspector forbidden")
    if (os.name != "posix" or any(not getattr(os, flag, 0) for flag in
            ("O_NOFOLLOW", "O_DIRECTORY", "O_NONBLOCK", "O_CLOEXEC"))
            or os.open not in getattr(os, "supports_dir_fd", ())):
        raise JobRejected("Linux dirfd/no-follow protections required")
    root_parts = _path_parts(os.fspath(root), absolute=True)
    leaf_parts = _path_parts(entry["path"])
    fd = os.open("/", DIR_FLAGS)
    try:
        _dir_ok(fd)
        for part in root_parts + leaf_parts[:-1]:
            next_fd = _open_dir(fd, part)
            os.close(fd)
            fd = next_fd
        source_fd = os.open(leaf_parts[-1], FILE_FLAGS, dir_fd=fd)
        try:
            before = os.fstat(source_fd)
            if (not stat.S_ISREG(before.st_mode) or before.st_uid not in (0, os.getuid())
                    or before.st_mode & 0o022 or before.st_nlink != 1
                    or before.st_size > MAX_SOURCE):
                raise JobRejected("unsafe, linked, or oversized source")
            data = os.read(source_fd, MAX_SOURCE + 1)
            after = os.fstat(source_fd)
            stable = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
            if len(data) > MAX_SOURCE or stable(before) != stable(after) or len(data) != before.st_size:
                raise JobRejected("source mutated or exceeded bound during read")
        finally:
            os.close(source_fd)
    finally:
        os.close(fd)
    blob = hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\x00" + data).hexdigest()
    if not hmac.compare_digest(blob, entry["git_blob_sha1"]):
        raise JobRejected("source does not match pinned Git blob")
    try:
        data.decode("utf-8")
    except UnicodeError as exc:
        raise JobRejected("source is not UTF-8 text") from exc
    return data


def capture_pinned_source(jobs, root, policy, source_id, job_id):
    """Read allowlisted bytes and commit a durable local checksum job once.

    Policy is installed by the operator, never supplied by an untrusted caller.
    The job's only executable is the already-reviewed sha256-echo builtin.
    """
    if not isinstance(jobs, ResearchJobs) or type(policy) is not dict:
        raise JobRejected("reviewed job engine and operator policy required")
    if type(source_id) is not str or ID.fullmatch(source_id) is None or source_id not in policy:
        raise JobRejected("source id not allowlisted")
    validated = {key: _policy_entry(value) for key, value in policy.items() if type(key) is str and ID.fullmatch(key)}
    if len(validated) != len(policy):
        raise JobRejected("invalid source policy key")
    entry = validated[source_id]
    data = _read_pinned(root, entry)
    observed = datetime.now(timezone.utc).isoformat(timespec="microseconds")
    digest = hashlib.sha256(data).hexdigest()
    receipt_job = jobs.run_once({"project": "RustWorld", "job_id": job_id,
                                 "command": "sha256-echo", "input_sha256": digest}, data)
    receipt = receipt_job["receipt"]
    if receipt["exit_status"] != 0 or receipt["input_sha256"] != digest:
        raise UntrustedReceipt("unexpected local checksum job")
    capture = {
        "schema": "baton.pinned_source.v1", "repository": REPO,
        "branch_claim": BRANCH, "commit_claim": entry["commit_sha"],
        "source_id": source_id, "path": entry["path"],
        "git_blob_sha1": entry["git_blob_sha1"], "content_sha256": digest,
        "source_bytes": len(data), "policy_sha256": hashlib.sha256(canonical(validated)).hexdigest(),
        "job_receipt_sha256": hashlib.sha256(canonical(receipt)).hexdigest(),
        "adapter_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "observed_utc": observed, "evidence": EVIDENCE,
    }
    mac = hmac.new(jobs.key, DOMAIN + canonical(capture), hashlib.sha256).hexdigest()
    return {"capture": capture, "capture_mac": mac, "source_text": data.decode("utf-8"), "job": receipt_job}


def verify_pinned_source(jobs, policy, bundle):
    """Check local record integrity, not Git commit ancestry or host identity."""
    if not isinstance(jobs, ResearchJobs) or type(bundle) is not dict or set(bundle) != {"capture", "capture_mac", "source_text", "job"}:
        raise UntrustedReceipt("invalid source bundle")
    c, mac, raw, job = (bundle[k] for k in ("capture", "capture_mac", "source_text", "job"))
    if type(c) is not dict or type(mac) is not str or type(raw) is not str or type(job) is not dict:
        raise UntrustedReceipt("invalid source bundle values")
    try:
        if not hmac.compare_digest(hmac.new(jobs.key, DOMAIN + canonical(c), hashlib.sha256).hexdigest(), mac):
            raise ValueError("source receipt MAC mismatch")
        entry = _policy_entry(policy[c["source_id"]])
        data = raw.encode("utf-8")
        if len(data) > MAX_SOURCE:
            raise ValueError("oversized source")
        blob = hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\x00" + data).hexdigest()
        expected = {"schema": "baton.pinned_source.v1", "repository": REPO,
                    "branch_claim": BRANCH, "commit_claim": entry["commit_sha"],
                    "source_id": c["source_id"], "path": entry["path"],
                    "git_blob_sha1": entry["git_blob_sha1"],
                    "content_sha256": hashlib.sha256(data).hexdigest(), "source_bytes": len(data),
                    "policy_sha256": hashlib.sha256(canonical({k: _policy_entry(v) for k, v in policy.items()})).hexdigest(),
                    "job_receipt_sha256": hashlib.sha256(canonical(job["receipt"])).hexdigest(),
                    "adapter_source_sha256": c["adapter_source_sha256"],
                    "observed_utc": c["observed_utc"], "evidence": EVIDENCE}
        if (c != expected or blob != entry["git_blob_sha1"]
                or type(c["adapter_source_sha256"]) is not str
                or re.fullmatch(r"[0-9a-f]{64}", c["adapter_source_sha256"]) is None):
            raise ValueError("source metadata mismatch")
        stored = jobs.audit("RustWorld", job["receipt"]["job_id"])
        if (stored["state"] != "completed_local_only" or stored["receipt"] != job["receipt"]
                or stored["mac"] != job["mac"] or stored["output"] != job["output"]
                or stored["receipt"]["input_sha256"] != c["content_sha256"]):
            raise ValueError("durable job mismatch")
        datetime.fromisoformat(c["observed_utc"])
    except (KeyError, TypeError, ValueError, JobRejected, UntrustedReceipt) as exc:
        raise UntrustedReceipt("source bundle fails pinned audit") from exc
    return {"state": "verified_local_pinned_blob_only", "content_sha256": c["content_sha256"],
            "git_blob_sha1": c["git_blob_sha1"], "source_bytes": c["source_bytes"]}
