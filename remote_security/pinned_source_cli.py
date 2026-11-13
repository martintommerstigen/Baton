"""One-shot, read-only RustWorld source inspection; no shell or network API.

Operator supplies a private receipt key, private evidence directory, local
archive checkout and a unique job ID. Caller selects only one of three
immutable source IDs pinned to the archived GTRCM/RustWorld commit.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from remote_security.pinned_source import capture_pinned_source
from remote_security.pinned_source_bundle import save_pinned_bundle, load_pinned_bundle
from remote_security.research_jobs import (
    ResearchJobs, JobRejected, JobUncertain, UntrustedReceipt, _load_receipt_key,
)

ARCHIVE_COMMIT = "94bed1f667179c6b9501a10ab34d2cca883f8760"
PINNED_POLICY = {
    "rustworld-network": {
        "path": "source/Dokumenter/relational_core/src/network.rs",
        "git_blob_sha1": "a851241df6a227056a99878260eb0d9559dd4975",
        "commit_sha": ARCHIVE_COMMIT, "branch": "RustWorld",
    },
    "rustworld-world": {
        "path": "source/Dokumenter/kindergarden/src/world.rs",
        "git_blob_sha1": "8e579d97456641e626dc56bf34505713aab46e72",
        "commit_sha": ARCHIVE_COMMIT, "branch": "RustWorld",
    },
    "rustworld-node": {
        "path": "source/Dokumenter/kindergarden/src/node.rs",
        "git_blob_sha1": "8eedf7a0cfe5643bbe028720f2d37b0064c6fb4f",
        "commit_sha": ARCHIVE_COMMIT, "branch": "RustWorld",
    },
}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("capture", "audit"))
    parser.add_argument("--database", required=True)
    parser.add_argument("--receipt-key-file", required=True)
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--source-root", help="absolute path to local GTRCM RustWorld archive checkout")
    parser.add_argument("--source-id", choices=sorted(PINNED_POLICY))
    parser.add_argument("--job-id")
    args = parser.parse_args(argv)
    if os.geteuid() == 0:
        parser.error("run as a dedicated unprivileged user, never root")
    if args.action == "capture" and not (args.source_root and args.source_id and args.job_id):
        parser.error("capture requires source-root, source-id and unique job-id")
    if args.action == "audit" and (args.source_root or args.job_id):
        parser.error("audit accepts only stored evidence, not source-root or job-id")
    try:
        jobs = ResearchJobs(args.database, _load_receipt_key(args.receipt_key_file),
                            {"RustWorld": ["sha256-echo"]}, audit_only=args.action == "audit")
        if args.action == "capture":
            bundle = capture_pinned_source(jobs, args.source_root, PINNED_POLICY,
                                           args.source_id, args.job_id)
            result = save_pinned_bundle(jobs, PINNED_POLICY, bundle, args.evidence)
            result.update({"source_id": args.source_id, "content_sha256": bundle["capture"]["content_sha256"],
                           "evidence": "local_pinned_blob_only_not_host_or_physics_attestation"})
        else:
            checked = load_pinned_bundle(jobs, PINNED_POLICY, args.evidence)
            if args.source_id and checked["bundle"]["capture"]["source_id"] != args.source_id:
                raise UntrustedReceipt("source ID does not match audit request")
            result = dict(checked["verification"], evidence_sha256=checked["evidence_sha256"])
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except (JobRejected, JobUncertain, UntrustedReceipt, OSError, ValueError, PermissionError) as exc:
        # Never print source bytes, private paths, receipt key or exception text.
        print(json.dumps({"state": "rejected_or_uncertain_no_retry", "error_type": type(exc).__name__}), file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
