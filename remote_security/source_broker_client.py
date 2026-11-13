"""B5 fixed-ID read-only RPC client; binds source/job receipt to one request.

Uses the existing B5 SO_PEERCRED gate BEFORE sending bytes. Never retries an
uncertain request, exposes arbitrary paths, or authorizes browser/UI writes.
"""
from __future__ import annotations

import re

from remote_security.broker_peer import BrokerUncertain, query_verified_broker
from remote_security.pinned_source_cli import PINNED_POLICY

JOB_ID = re.compile(r"[A-Za-z0-9_-]{8,64}\Z")
SHA = re.compile(r"[0-9a-f]{64}\Z")
RESPONSE_KEYS = frozenset({"state", "source_id", "job_id", "source_sha256", "evidence_sha256"})


def request_pinned_source(socket_path, expected_uid, action, source_id, job_id, *, timeout=3.0):
    """One-shot request; success proves only a matching local pinned-byte receipt."""
    if (type(action) is not str or action not in ("capture", "audit")
            or type(source_id) is not str or source_id not in PINNED_POLICY
            or type(job_id) is not str or JOB_ID.fullmatch(job_id) is None):
        raise ValueError("fixed source action/id and unique job ID required")
    request = {"version": 1, "action": action, "source_id": source_id, "job_id": job_id}
    response = query_verified_broker(socket_path, expected_uid, request, timeout=timeout)
    expected_state = ("completed_local_pinned_source" if action == "capture"
                      else "verified_local_pinned_source")
    if (type(response) is not dict or set(response) != RESPONSE_KEYS
            or response.get("state") != expected_state
            or response.get("source_id") != source_id
            or response.get("job_id") != job_id
            or any(type(response.get(k)) is not str or SHA.fullmatch(response[k]) is None
                   for k in ("source_sha256", "evidence_sha256"))):
        raise BrokerUncertain("source broker reply invalid/uncertain; never retry automatically")
    return response
