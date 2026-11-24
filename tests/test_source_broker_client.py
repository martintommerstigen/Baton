"""B5 client response binding; no implicit retry or UI authority."""
import unittest
from unittest.mock import patch
from remote_security.source_broker_client import request_pinned_source, BrokerUncertain


def reply(state="completed_local_pinned_source", source_id="rustworld-world", job_id="source0001"):
    return {"state": state, "source_id": source_id, "job_id": job_id,
            "source_sha256": "a" * 64, "evidence_sha256": "b" * 64}


class ClientTests(unittest.TestCase):
    @patch("remote_security.source_broker_client.query_verified_broker")
    def test_capture_and_audit_bind_exact_request(self, query):
        query.return_value = reply()
        self.assertEqual(request_pinned_source("/run/baton/read.sock", 1001, "capture", "rustworld-world", "source0001"), reply())
        self.assertEqual(query.call_args.args[2], {"version": 1, "action": "capture", "source_id": "rustworld-world", "job_id": "source0001"})
        query.return_value = reply("verified_local_pinned_source")
        self.assertEqual(request_pinned_source("/run/baton/read.sock", 1001, "audit", "rustworld-world", "source0001")["state"], "verified_local_pinned_source")

    @patch("remote_security.source_broker_client.query_verified_broker")
    def test_invalid_request_rejected_before_socket(self, query):
        for action, source_id, job_id in (("exec", "rustworld-world", "source0001"),
                                          ("capture", "other", "source0001"),
                                          ("capture", "rustworld-world", "../bad")):
            with self.subTest(action=action, source_id=source_id), self.assertRaises(ValueError):
                request_pinned_source("/run/baton/read.sock", 1001, action, source_id, job_id)
        query.assert_not_called()

    @patch("remote_security.source_broker_client.query_verified_broker")
    def test_forged_or_stale_response_is_uncertain_without_retry(self, query):
        invalid = [reply(source_id="rustworld-node"), reply(job_id="source9999"),
                   reply(state="verified_local_pinned_source"), reply(state="rejected_or_uncertain_no_retry"),
                   dict(reply(), source_sha256="0"), dict(reply(), evidence_sha256="Z" * 64),
                   dict(reply(), extra="unexpected"), {"state": "completed_local_pinned_source"}]
        for result in invalid:
            query.return_value = result
            query.reset_mock()
            with self.subTest(result=result), self.assertRaises(BrokerUncertain):
                request_pinned_source("/run/baton/read.sock", 1001, "capture", "rustworld-world", "source0001")
            self.assertEqual(query.call_count, 1)

    @patch("remote_security.source_broker_client.query_verified_broker")
    def test_kernel_peer_rejection_propagates_without_fallback(self, query):
        query.side_effect = BrokerUncertain("peer identity mismatch")
        with self.assertRaises(BrokerUncertain):
            request_pinned_source("/run/baton/read.sock", 1001, "capture", "rustworld-world", "source0001")
        self.assertEqual(query.call_count, 1)
