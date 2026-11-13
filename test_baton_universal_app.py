import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from baton_outbox import (create_store, draft_message, approve_message,
                          mark_attempted, record_transport_outcome,
                          get_messages, get_events)
from baton_provider_catalog import (provider_catalog, installed_capabilities,
                                    can_request_device_access)


class ModelConnectionTests(unittest.TestCase):
    def test_provider_catalog_is_extensible_without_false_auth(self):
        catalog = provider_catalog()
        self.assertIn("chatgpt", [p.key for p in catalog])
        self.assertIn("mcp", [p.key for p in catalog])
        self.assertIn("ollama", [p.key for p in catalog])
        self.assertEqual(installed_capabilities("ollama", core_live=True,
                                                mcp_configured=True)["device_exec"], False)
        self.assertFalse(installed_capabilities("chatgpt", core_live=True,
                                                 mcp_configured=False)["device_exec"])
        for item in catalog:
            self.assertFalse(installed_capabilities(item.key, core_live=True,
                                                     mcp_configured=True)["external_post"])

    def test_authorization_gate(self):
        all_true = dict(core_live=True, authenticated=True, user_approved=True,
                        local_mcp_capable=True, revoked=False)
        self.assertTrue(can_request_device_access(**all_true))
        for field in ("core_live","authenticated","user_approved","local_mcp_capable"):
            altered = dict(all_true)
            altered[field] = False
            self.assertFalse(can_request_device_access(**altered), field)
        self.assertFalse(can_request_device_access(**dict(all_true, revoked=True)))


class OutboxTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "outbox.sqlite"
        self.conn = create_store(self.path)
        self.addCleanup(self.conn.close)

    def test_draft_is_not_sent(self):
        mid = draft_message(self.conn, "model", "recipient-A", "hello", "Baton:unverified")
        row = get_messages(self.conn)[0]
        self.assertEqual(row["state"], "draft")
        self.assertEqual(row["delivery_proof"], None)
        self.assertEqual(row["origin"], "Baton:unverified")
        self.assertEqual(get_events(self.conn, mid), [("drafted","not-delivered")])
        self.assertTrue(self.path.is_file())

    def test_transport_receipt_distinct_from_approval(self):
        mid = draft_message(self.conn, "social", "@recipient", "hello", "local:human")
        approve_message(self.conn, mid)
        self.assertEqual(get_messages(self.conn)[0]["state"], "approved")
        with self.assertRaises(ValueError):
            record_transport_outcome(self.conn, mid, success=True, proof="fake receipt")
        mark_attempted(self.conn, mid, "test-adapter")
        record_transport_outcome(self.conn, mid, success=True, proof="transport-id-123")
        self.assertEqual(get_messages(self.conn)[0]["state"], "delivered")
        self.assertEqual([e[0] for e in get_events(self.conn, mid)],
                         ["drafted","owner-approved","send-attempted","transport-delivered"])
        with self.assertRaises(ValueError):
            mark_attempted(self.conn, mid, "test-adapter")

    def test_no_unapproved_send_or_unsupported_channel(self):
        mid = draft_message(self.conn, "email", "a@example.invalid", "hello", "human")
        with self.assertRaises(ValueError):
            mark_attempted(self.conn, mid, "test-adapter")
        with self.assertRaises(ValueError):
            draft_message(self.conn, "anything", "recipient", "body", "human")

    def test_failed_transport_not_read_or_reply(self):
        mid = draft_message(self.conn, "chat", "remote", "hello", "Baton")
        approve_message(self.conn, mid)
        mark_attempted(self.conn, mid, "fake")
        record_transport_outcome(self.conn, mid, success=False, proof="network-failed")
        self.assertEqual(get_messages(self.conn)[0]["state"], "failed")
        self.assertFalse(any("read" in action or "replied" in action
                             for action, _ in get_events(self.conn, mid)))

    def test_reject_symlink_to_store(self):
        symlink = Path(self.tmp.name) / "link.sqlite"
        symlink.symlink_to(self.path)
        with self.assertRaisesRegex(ValueError, "symlink"):
            create_store(symlink)


if __name__ == "__main__":
    unittest.main()
