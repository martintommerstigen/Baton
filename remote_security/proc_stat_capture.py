"""B5 read-only fixed Linux /proc/stat capture with durable job provenance.

This observes kernel-exposed counters, not a calibrated independent nature
measurement. It never accepts a caller-supplied path or executes a subprocess.
No browser, UI, broker admission, network or automatic retry is involved.
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
    ResearchJobs, JobRejected, UntrustedReceipt, canonical,
)

SOURCE = "/proc/stat"
KIND = "linux_proc_stat_aggregate_cpu_v1"
EVIDENCE = "local_kernel_counter_not_independent_nature_measurement"
MAX_LINE = 4096
_CPU_LINE = re.compile(rb"cpu[ \t]+[0-9]+(?:[ \t]+[0-9]+){3,19}\n\Z")
_HEX = re.compile(r"[0-9a-f]{64}\Z")
_DOMAIN = b"baton.proc_stat_capture.v1\x00"


def _validated_cpu_line(raw):
    if (type(raw) is not bytes or len(raw) > MAX_LINE
            or _CPU_LINE.fullmatch(raw) is None):
        raise JobRejected("invalid or oversized aggregate CPU counter line")
    return raw


def _read_proc_cpu_line():
    """Read only the first aggregate line from a fixed kernel-exposed source."""
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NONBLOCK", 0)
    fd = os.open(SOURCE, flags)
    try:
        s = os.fstat(fd)
        if not stat.S_ISREG(s.st_mode) or s.st_uid != 0:
            raise JobRejected("expected root-owned regular procfs counter")
        data = os.read(fd, MAX_LINE + 1)
        line, sep, _ = data.partition(b"\n")
        if not sep:
            raise JobRejected("missing bounded aggregate CPU line")
        return _validated_cpu_line(line + b"\n")
    finally:
        os.close(fd)


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _sign(key, capture):
    return hmac.new(key, _DOMAIN + canonical(capture), hashlib.sha256).hexdigest()


def capture_once(jobs, project, job_id):
    """Capture once; a crash or ambiguous outcome must never trigger retry."""
    if not isinstance(jobs, ResearchJobs):
        raise TypeError("reviewed ResearchJobs instance required")
    # No user-supplied source, shell command, URL, or executable is accepted.
    raw = _validated_cpu_line(_read_proc_cpu_line())
    observed = datetime.now(timezone.utc).isoformat(timespec="microseconds")
    request = {"project": project, "job_id": job_id, "command": "sha256-echo",
               "input_sha256": _sha(raw)}
    job = jobs.run_once(request, raw)
    receipt = job["receipt"]
    if receipt["exit_status"] != 0 or receipt["input_sha256"] != _sha(raw):
        raise UntrustedReceipt("unexpected builtin check result")
    capture = {
        "schema": "baton.proc_stat_capture.v1",
        "source": SOURCE,
        "source_kind": KIND,
        "project": project,
        "job_id": job_id,
        "command": "sha256-echo",
        "raw_sha256": _sha(raw),
        "raw_bytes": len(raw),
        "job_receipt_sha256": _sha(canonical(receipt)),
        "adapter_source_sha256": receipt["adapter_source_sha256"],
        "capture_module_sha256": _sha(Path(__file__).read_bytes()),
        "observed_utc": observed,
        "evidence": EVIDENCE,
    }
    return {"capture": capture, "capture_mac": _sign(jobs.key, capture),
            "raw_cpu_line": raw.decode("ascii"), "job": job}


def verify_capture(jobs, bundle):
    """Verify signed capture against a separately opened durable job receipt.

    A valid result proves only consistency with the local shared-secret key
    and the stored builtin check; it cannot establish kernel authenticity,
    physical independence, correct host identity or a ChatGPT wake.
    """
    if not isinstance(jobs, ResearchJobs) or type(bundle) is not dict:
        raise UntrustedReceipt("invalid verifier input")
    if set(bundle) != {"capture", "capture_mac", "raw_cpu_line", "job"}:
        raise UntrustedReceipt("capture bundle schema mismatch")
    capture, mac, raw_text, job = (bundle[k] for k in
                                 ("capture", "capture_mac", "raw_cpu_line", "job"))
    expected_keys = {
        "schema", "source", "source_kind", "project", "job_id", "command",
        "raw_sha256", "raw_bytes", "job_receipt_sha256",
        "adapter_source_sha256", "capture_module_sha256",
        "observed_utc", "evidence",
    }
    if type(capture) is not dict or set(capture) != expected_keys:
        raise UntrustedReceipt("capture metadata schema mismatch")
    if (capture["schema"] != "baton.proc_stat_capture.v1"
            or capture["source"] != SOURCE or capture["source_kind"] != KIND
            or capture["command"] != "sha256-echo"
            or capture["evidence"] != EVIDENCE):
        raise UntrustedReceipt("wrong capture provenance")
    if (type(mac) is not str or _HEX.fullmatch(mac) is None
            or not hmac.compare_digest(mac, _sign(jobs.key, capture))):
        raise UntrustedReceipt("capture MAC mismatch")
    if type(raw_text) is not str:
        raise UntrustedReceipt("raw source bytes missing")
    try:
        raw = _validated_cpu_line(raw_text.encode("ascii"))
        stamp = datetime.fromisoformat(capture["observed_utc"])
    except (ValueError, TypeError, UnicodeError, JobRejected) as exc:
        raise UntrustedReceipt("invalid source or observation time") from exc
    if stamp.tzinfo is None or stamp.utcoffset().total_seconds() != 0:
        raise UntrustedReceipt("UTC observation timestamp required")
    if (capture["raw_sha256"] != _sha(raw)
            or type(capture["raw_bytes"]) is not int
            or capture["raw_bytes"] != len(raw)
            or any(type(capture[k]) is not str or _HEX.fullmatch(capture[k]) is None
                   for k in ("job_receipt_sha256", "adapter_source_sha256",
                             "capture_module_sha256"))):
        raise UntrustedReceipt("raw data or source pointer mismatch")
    stored = jobs.audit(capture["project"], capture["job_id"])
    if stored.get("state") != "completed_local_only":
        raise UntrustedReceipt("no completed durable job receipt")
    if type(job) is not dict or set(job) != {"receipt", "mac", "output"}:
        raise UntrustedReceipt("job response schema mismatch")
    if job != {k: stored[k] for k in ("receipt", "mac", "output")}:
        raise UntrustedReceipt("job differs from durable receipt")
    receipt = stored["receipt"]
    if (capture["job_receipt_sha256"] != _sha(canonical(receipt))
            or capture["adapter_source_sha256"] != receipt["adapter_source_sha256"]
            or capture["project"] != receipt["project"]
            or capture["job_id"] != receipt["job_id"]
            or receipt["command"] != "sha256-echo"
            or receipt["input_sha256"] != _sha(raw)
            or receipt["exit_status"] != 0
            or stored["output"] != {"sha256": _sha(raw), "bytes": len(raw)}):
        raise UntrustedReceipt("capture and durable job mismatch")
    return {"state": "verified_local_kernel_counter_only",
            "source_sha256": _sha(raw),
            "job_receipt_sha256": capture["job_receipt_sha256"]}
