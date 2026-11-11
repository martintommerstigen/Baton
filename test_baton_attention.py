"""Negative and positive tests for recipient-owned Baton attention rules."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from baton_attention import (
    setup_attention, set_mode, get_mode, set_rule, remove_rule, list_rules,
    decide, receive, list_inbox, recent_audit, prune,
    MUTED_TTL_NS, VISIBLE_TTL_NS, REPLAY_TTL_NS
)
from baton_outbox import create_store

OWNER = "local:olliver"
OTHER = "local:friend"


class AttentionTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = create_store(Path(self.temp.name) / "inbox.sqlite")
        self.addCleanup(self.db.close)
        setup_attention(self.db)

    def message(self, source_id, *, sender_id="provider:alice", body="Hello",
                topics=(), sender_verified=True, topics_trusted=False):
        return receive(self.db, OWNER, source_id=source_id, channel="model",
                       sender_id=sender_id, body=body, topics=topics,
                       sender_verified=sender_verified, topics_trusted=topics_trusted,
                       now_ns=1000)

    def test_open_default_and_no_receipt_inferred(self):
        self.assertEqual(get_mode(self.db, OWNER), "open")
        result = self.message("transport:1")
        self.assertEqual(result["decision"], "pass")
        self.assertEqual(len(list_inbox(self.db, OWNER)), 1)
        self.assertEqual(recent_audit(self.db, OWNER)[0]["decision"], "pass")
        self.assertEqual(result["status"], "filtered")
        self.assertNotIn("delivered", str(result))
        self.assertNotIn("replied", str(result))

    def test_verified_allowlist_and_spoofed_identity(self):
        set_mode(self.db, OWNER, "allowlist")
        set_rule(self.db, OWNER, "identity", "provider:alice", "allow")
        self.assertEqual(
            decide(self.db, OWNER, sender_id="provider:alice", sender_verified=True)["decision"],
            "pass"
        )
        self.assertEqual(
            decide(self.db, OWNER, sender_id="provider:alice", sender_verified=False)["decision"],
            "mute"
        )
        self.assertEqual(
            decide(self.db, OWNER, sender_id="provider:bob", sender_verified=True)["decision"],
            "mute"
        )
        self.assertEqual(get_mode(self.db, OTHER), "open")

    def test_topics_sender_claim_cannot_bypass_allowlist(self):
        set_mode(self.db, OWNER, "allowlist")
        set_rule(self.db, OWNER, "topic", "astrophysics", "allow")
        self.assertEqual(
            decide(self.db, OWNER, sender_id="provider:any",
                   topics=["ASTROPHYSICS"], topics_trusted=False)["decision"], "mute"
        )
        self.assertEqual(
            decide(self.db, OWNER, sender_id="provider:any",
                   topics=["AstroPhysics"], topics_trusted=True)["decision"], "pass"
        )

    def test_block_outweighs_allow_for_verified_principal(self):
        set_mode(self.db, OWNER, "allowlist")
        set_rule(self.db, OWNER, "identity", "provider:alice", "allow")
        set_rule(self.db, OWNER, "topic", "spam", "block")
        result = self.message("transport:spam", body="Should never be stored",
                              topics=["SPAM"])
        self.assertEqual(result["decision"], "block")
        self.assertEqual(list_inbox(self.db, OWNER, include_muted=True), [])
        self.assertEqual(self.db.execute("SELECT count(*) FROM attention_inbox").fetchone()[0], 0)
        self.assertEqual(recent_audit(self.db, OWNER)[0]["reason"], "matched-topic")
        # No sender identity or body stored in the audit table.
        self.assertNotIn("Should never", str(recent_audit(self.db, OWNER)))
        self.assertNotIn("provider:alice", str(recent_audit(self.db, OWNER)))

    def test_keyword_mute_and_block(self):
        mute_id = set_rule(self.db, OWNER, "keyword", "Sale TODAY", "mute")
        first = self.message("transport:sale", body="Huge SALE today!")
        self.assertEqual(first["decision"], "mute")
        self.assertEqual(list_inbox(self.db, OWNER), [])
        self.assertEqual(len(list_inbox(self.db, OWNER, include_muted=True)), 1)
        self.assertTrue(remove_rule(self.db, OWNER, mute_id))
        self.assertFalse(remove_rule(self.db, OTHER, mute_id))
        set_rule(self.db, OWNER, "keyword", "sale today", "block")
        self.assertEqual(self.message("transport:sale2",
                                      body="Huge sale today!")["decision"], "block")

    def test_mute_not_transport_failure_or_refusal(self):
        set_rule(self.db, OWNER, "identity", "provider:alice", "mute")
        verdict = self.message("transport:quiet")
        self.assertEqual(verdict["decision"], "mute")
        self.assertNotIn("refused", str(verdict))
        self.assertNotIn("failed", str(verdict))
        self.assertEqual(list_inbox(self.db, OWNER, include_muted=True)[0]["state"], "muted")

    def test_duplicate_no_inbox_or_audit_duplication(self):
        first = self.message("transport:uniq")
        second = self.message("transport:uniq", body="DIFFERENT CONTENT")
        self.assertEqual(second, {"status": "duplicate", "original_decision": "pass"})
        self.assertEqual(len(list_inbox(self.db, OWNER, include_muted=True)), 1)
        self.assertEqual(len(recent_audit(self.db, OWNER)), 1)
        self.assertNotIn("DIFFERENT CONTENT", str(list_inbox(self.db, OWNER, include_muted=True)))
        self.assertNotEqual(first["decision_id"], "")

    def test_same_transport_id_from_different_sender_is_not_duplicate(self):
        first = self.message("transport:shared-id", sender_id="provider:alice")
        second = self.message("transport:shared-id", sender_id="provider:bob")
        self.assertEqual(first["status"], "filtered")
        self.assertEqual(second["status"], "filtered")
        self.assertEqual(len(recent_audit(self.db, OWNER)), 2)

    def test_retention_expiration_and_bounded_replay(self):
        set_rule(self.db, OWNER, "keyword", "ignore-me", "mute")
        self.message("transport:muted", body="ignore-me")
        self.message("transport:normal", body="normal")
        removed = prune(self.db, now_ns=1000 + MUTED_TTL_NS + 1)
        self.assertEqual(removed["expired_bodies"], 1)
        self.assertEqual(len(list_inbox(self.db, OWNER, include_muted=True)), 1)
        removed = prune(self.db, now_ns=1000 + VISIBLE_TTL_NS + 1)
        self.assertEqual(removed["expired_bodies"], 1)
        self.assertEqual(len(recent_audit(self.db, OWNER)), 2)
        prune(self.db, now_ns=1000 + REPLAY_TTL_NS + 1)
        self.assertEqual(recent_audit(self.db, OWNER), [])

    def test_malformed_rules_and_provider_scoped_identity(self):
        with self.assertRaisesRegex(ValueError, "provider-scoped"):
            set_rule(self.db, OWNER, "identity", "Alice", "allow")
        with self.assertRaises(ValueError):
            set_rule(self.db, OWNER, "topic", "Astrophysics", "execute")
        with self.assertRaises(ValueError):
            set_rule(self.db, OWNER, "keyword", "", "mute")
        with self.assertRaises(ValueError):
            set_mode(self.db, OWNER, "open-to-all-programs")
        with self.assertRaises(ValueError):
            receive(self.db, OWNER, source_id="x", channel="model",
                    sender_id="provider:any", body="hi",
                    sender_verified="yes")

    def test_rule_overwrite_and_delete(self):
        rid = set_rule(self.db, OWNER, "topic", "Søvn", "mute")
        again = set_rule(self.db, OWNER, "topic", "søvn", "block")
        self.assertEqual(rid, again)
        self.assertEqual(len(list_rules(self.db, OWNER)), 1)
        self.assertEqual(list_rules(self.db, OWNER)[0]["action"], "block")
        self.assertTrue(remove_rule(self.db, OWNER, rid))
        self.assertEqual(list_rules(self.db, OWNER), [])


if __name__ == "__main__":
    unittest.main()
