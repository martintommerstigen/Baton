"""Offline adversarial tests of source-use registration, NOT real authentication."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
import sqlite3
import tempfile
import unittest

from baton_use_claims_reference import UseClaimLedger, VerifiedGrant


class LocalForumFixture:
    """Minimal SQLite Forum-compatible fixture, no UI, network or send."""
    def __init__(self, path):
        self.path = path
        with self.connect() as c:
            c.executescript("""CREATE TABLE observations(
                observation_id INTEGER PRIMARY KEY,topic_id TEXT NOT NULL,
                source_chat_id TEXT NOT NULL,source_message_id TEXT NOT NULL,
                body_sha256 TEXT NOT NULL);
                INSERT INTO observations VALUES
                (1,'source','chat:A','turn:A','hash-A'),
                (2,'downstream','chat:B','turn:B','hash-B'),
                (3,'source','chat:C','turn:C','hash-C');""")

    @contextmanager
    def connect(self):
        c = sqlite3.connect(str(self.path), timeout=10)
        try:
            c.execute("PRAGMA foreign_keys=ON")
            c.execute("PRAGMA busy_timeout=10000")
            with c:
                yield c
        finally:
            c.close()


class TestCoreVerifier:
    """Simulated trusted Core: only preapproved token/scope pairs verify."""
    def __init__(self):
        self.grants = {}

    def allow(self, token, *, scope, principal="test:authorized", action="a"*32):
        self.grants[token] = VerifiedGrant(principal_id=principal,
            grant_id="b"*32,grant_epoch=7,action_id=action,scope_digest=scope)

    def __call__(self, claim, token):
        grant = self.grants.get(token)
        if grant is None or grant.scope_digest != claim["scope_digest"]:
            raise PermissionError("untrusted, revoked or out-of-scope token")
        return grant


class UseClaimSecurityTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.forum = LocalForumFixture(Path(temp.name)/"forum.sqlite3")
        self.core = TestCoreVerifier()
        self.ledger = UseClaimLedger(self.forum,verifier=self.core)
        self.ledger.setup()

    def proposal(self, *, upstream=1, proposal_id=None, key="support-alpha"):
        return self.ledger.propose(2,upstream,use_key=key,
            use_mode="supports_claim",premise_key="premise-alpha",
            proposal_id=proposal_id)

    def scope(self, proposal_id):
        with self.forum.connect() as c:
            return c.execute("SELECT scope_digest FROM source_use_proposals WHERE proposal_id=?",
                             (proposal_id,)).fetchone()[0]

    def test_unauthorized_first_writer_identical_payload_cannot_steal_attestation(self):
        untrusted = self.proposal(proposal_id="1"*32)
        authorized = self.proposal(proposal_id="2"*32)
        self.assertNotEqual(untrusted,authorized)
        with self.assertRaises(PermissionError):
            self.ledger.attest(untrusted,"forged-token")
        self.core.allow("valid",scope=self.scope(authorized))
        self.ledger.attest(authorized,"valid")
        group = self.ledger.list_for_downstream(2)[0]
        self.assertEqual(group["status"],"attested")
        self.assertIsNone(group["canonical_use_id"])
        self.assertEqual([len(p["attestations"]) for p in group["proposals"]],[0,1])
        with self.forum.connect() as c:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM source_use_attestations").fetchone()[0],1)

    def test_unauthorized_conflicting_first_writer_does_not_reserve_use_key(self):
        untrusted = self.proposal(upstream=3,proposal_id="1"*32)
        authorized = self.proposal(upstream=1,proposal_id="2"*32)
        self.core.allow("valid",scope=self.scope(authorized))
        self.ledger.attest(authorized,"valid")
        group = self.ledger.list_for_downstream(2)[0]
        self.assertEqual(group["status"],"attested")
        self.assertEqual(len(group["proposals"]),2)
        self.assertEqual(group["proposals"][0]["upstream_id"],3)

    def test_two_authorized_conflicting_uses_are_disputed_in_either_order(self):
        first = self.proposal(upstream=1,proposal_id="1"*32)
        second = self.proposal(upstream=3,proposal_id="2"*32)
        self.core.allow("first",scope=self.scope(first),action="1"*32)
        self.core.allow("second",scope=self.scope(second),
                        principal="test:other-reviewer",action="2"*32)
        self.ledger.attest(second,"second")
        self.ledger.attest(first,"first")
        before = self.ledger.list_for_downstream(2)[0]
        self.assertEqual(before["status"],"registration_disputed")
        self.assertIsNone(before["canonical_use_id"])
        self.assertEqual({p["upstream_id"] for p in before["proposals"]},{1,3})
        # The same two grants, inserted in reverse order in a fresh ledger.
        with tempfile.TemporaryDirectory() as td:
            forum2 = LocalForumFixture(Path(td)/"forum.sqlite3")
            core2 = TestCoreVerifier()
            ledger2 = UseClaimLedger(forum2,verifier=core2)
            ledger2.setup()
            for upstream,pid,token,action in [(1,first,"first","1"*32),
                                               (3,second,"second","2"*32)]:
                ledger2.propose(2,upstream,use_key="support-alpha",
                    use_mode="supports_claim",premise_key="premise-alpha",proposal_id=pid)
                core2.allow(token,scope=self.scope(pid),action=action)
                ledger2.attest(pid,token)
            after = ledger2.list_for_downstream(2)[0]
            self.assertEqual(before["status"],after["status"])
            self.assertEqual({p["upstream_id"] for p in before["proposals"]},
                             {p["upstream_id"] for p in after["proposals"]})

    def test_action_replay_is_idempotent_but_cannot_rebind(self):
        first = self.proposal(proposal_id="1"*32)
        second = self.proposal(proposal_id="2"*32)
        self.core.allow("first",scope=self.scope(first),action="a"*32)
        self.core.allow("second",scope=self.scope(second),action="a"*32)
        x = self.ledger.attest(first,"first")
        self.assertEqual(x,self.ledger.attest(first,"first"))
        with self.assertRaises(ValueError):
            self.ledger.attest(second,"second")

    def test_unverified_and_wrong_scope_grants_fail_closed(self):
        p = self.proposal()
        self.core.allow("wrong",scope="0"*64)
        with self.assertRaises(PermissionError):
            self.ledger.attest(p,"wrong")
        with self.assertRaises(PermissionError):
            self.ledger.attest(p,"missing")
        no_core = UseClaimLedger(self.forum)
        with self.assertRaises(PermissionError):
            no_core.attest(p,"anything")
        self.assertEqual(self.ledger.list_for_downstream(2)[0]["status"],"proposed_only")

    def test_source_turn_mutation_invalidates_scope(self):
        p = self.proposal()
        self.core.allow("valid",scope=self.scope(p))
        with self.forum.connect() as c:
            c.execute("UPDATE observations SET body_sha256='tampered' WHERE observation_id=2")
        with self.assertRaises(ValueError):
            self.ledger.attest(p,"valid")

    def test_proposal_id_cannot_be_reinterpreted(self):
        p = self.proposal(proposal_id="1"*32)
        self.assertEqual(p,self.proposal(proposal_id="1"*32))
        with self.assertRaises(ValueError):
            self.proposal(upstream=3,proposal_id="1"*32)

    def test_concurrent_same_authorized_action_only_one_attestation(self):
        p = self.proposal()
        self.core.allow("valid",scope=self.scope(p))
        with ThreadPoolExecutor(max_workers=4) as pool:
            ids = list(pool.map(lambda _: self.ledger.attest(p,"valid"),range(8)))
        self.assertEqual(len(set(ids)),1)
        with self.forum.connect() as c:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM source_use_attestations").fetchone()[0],1)


if __name__ == "__main__":
    unittest.main()
