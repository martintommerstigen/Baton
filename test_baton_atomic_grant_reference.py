"""Negative controls for atomic *local* grant attestation/revocation.

These use a temporary SQLite database and simulated trusted issuer/revoker.
No ChatGPT login, external effect, Greg installation or UI write is performed.
"""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import threading
import unittest

from baton_use_claims_reference import UseClaimLedger
from baton_atomic_grant_reference import SameDatabaseGrantAuthority
from test_baton_use_claims_reference import LocalForumFixture


class SameDatabaseGrantTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.forum = LocalForumFixture(Path(tmp.name) / "forum.sqlite3")
        self.authority = SameDatabaseGrantAuthority(
            self.forum,
            issuer=lambda claim, evidence: evidence == "trusted-issuer",
            revoker=lambda claim, evidence: evidence == "trusted-revoker")
        self.authority.setup()
        self.ledger = UseClaimLedger(self.forum)
        self.ledger.setup()
        self.authority.bind(self.ledger)
        self.grant_id = "b" * 32

    def proposal(self, *, upstream=1, pid="1"*32):
        return self.ledger.propose(2, upstream, use_key="support-alpha",
            use_mode="supports_claim", premise_key="premise-alpha",
            proposal_id=pid)

    def scope(self, proposal):
        with self.forum.connect() as c:
            return c.execute(
                "SELECT scope_digest FROM source_use_proposals WHERE proposal_id=?",
                (proposal,)).fetchone()[0]

    def issue(self, proposal, *, grant_id=None, epoch=7, evidence="trusted-issuer"):
        return self.authority.issue(
            grant_id=grant_id or self.grant_id,
            principal_id="test:authorized-reviewer",
            scope_digest=self.scope(proposal),
            grant_epoch=epoch,
            issue_action_id="c"*32 if grant_id is None else "d"*32,
            evidence=evidence)

    def evidence(self, *, grant_id=None, epoch=7, action="a"*32):
        return {"grant_id":grant_id or self.grant_id,
                "grant_epoch":epoch, "action_id":action}

    def test_no_trusted_issuer_or_revoker_cannot_grant_or_revoke(self):
        p = self.proposal()
        with self.assertRaises(PermissionError):
            self.issue(p, evidence="claimed-authority")
        with self.assertRaises(PermissionError):
            self.ledger.attest(p,self.evidence())
        self.issue(p)
        with self.assertRaises(PermissionError):
            self.authority.revoke(self.grant_id,evidence="claimed-owner")
        self.assertEqual(self.authority.attestation_status(123),None)

    def test_revoked_before_attestation_denies_without_claiming_rejection(self):
        p = self.proposal()
        self.issue(p)
        self.assertTrue(self.authority.revoke(
            self.grant_id,evidence="trusted-revoker"))
        with self.assertRaises(PermissionError):
            self.ledger.attest(p,self.evidence())
        self.assertEqual(self.ledger.list_for_downstream(2)[0]["status"],
                         "proposed_only")
        self.assertFalse(self.authority.revoke(
            self.grant_id,evidence="trusted-revoker"))

    def test_attestation_before_revocation_remains_historical_not_current(self):
        p = self.proposal()
        self.issue(p)
        att = self.ledger.attest(p,self.evidence())
        self.assertTrue(self.authority.attestation_status(att)["currently_unrevoked"])
        self.assertTrue(self.authority.revoke(
            self.grant_id,evidence="trusted-revoker"))
        status = self.authority.attestation_status(att)
        self.assertTrue(status["historically_attested"])
        self.assertFalse(status["currently_unrevoked"])
        self.assertEqual(self.ledger.list_for_downstream(2)[0]["status"],
                         "attested")  # historical label, not fresh authority
        with self.assertRaises(PermissionError):
            self.ledger.attest(p,self.evidence(action="e"*32))

    def test_stale_epoch_and_wrong_scope_are_rejected(self):
        p1 = self.proposal()
        p2 = self.proposal(upstream=3,pid="2"*32)
        self.issue(p1)
        with self.assertRaises(PermissionError):
            self.ledger.attest(p1,self.evidence(epoch=6))
        with self.assertRaises(PermissionError):
            self.ledger.attest(p2,self.evidence())
        self.assertEqual(self.ledger.list_for_downstream(2)[0]["status"],
                         "proposed_only")

    def test_duplicate_grant_cannot_be_renewed_with_new_epoch(self):
        p = self.proposal()
        self.issue(p)
        with self.assertRaises(Exception):
            self.issue(p,epoch=8)
        self.assertTrue(self.authority.revoke(
            self.grant_id,evidence="trusted-revoker"))
        with self.assertRaises(Exception):
            self.issue(p,epoch=8)

    def test_wrong_database_binding_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            other = LocalForumFixture(Path(tmp)/"other.sqlite3")
            other_ledger = UseClaimLedger(other)
            other_ledger.setup()
            with self.assertRaises(ValueError):
                self.authority.bind(other_ledger)

    def test_attestation_write_lock_serializes_revocation(self):
        p = self.proposal()
        self.issue(p)
        entered = threading.Event()
        release = threading.Event()
        revoker_entered = threading.Event()
        base_verify = self.authority.verify

        def delayed_verify(claim, evidence):
            entered.set()  # attest() already holds BEGIN IMMEDIATE
            if not release.wait(5):
                raise TimeoutError("test gate was not released")
            return base_verify(claim,evidence)

        def revoker(claim, evidence):
            revoker_entered.set()  # only after BEGIN IMMEDIATE acquired
            return evidence == "trusted-revoker"

        self.ledger.verifier = delayed_verify
        self.authority.revoker = revoker
        with ThreadPoolExecutor(max_workers=2) as pool:
            att_future = pool.submit(self.ledger.attest,p,self.evidence())
            self.assertTrue(entered.wait(3))
            rev_future = pool.submit(self.authority.revoke,self.grant_id,
                                     evidence="trusted-revoker")
            # Revoker cannot enter its transaction while attestation holds lock.
            self.assertFalse(revoker_entered.wait(0.15))
            release.set()
            att = att_future.result(timeout=6)
            self.assertTrue(rev_future.result(timeout=6))
        self.assertTrue(revoker_entered.is_set())
        self.assertFalse(self.authority.attestation_status(att)["currently_unrevoked"])
        self.assertTrue(self.authority.attestation_status(att)["historically_attested"])

    def test_reference_never_creates_operational_use_or_external_effect(self):
        p = self.proposal()
        self.issue(p)
        self.ledger.attest(p,self.evidence())
        result = self.ledger.list_for_downstream(2)[0]
        self.assertIsNone(result["canonical_use_id"])
        with self.forum.connect() as c:
            self.assertEqual(c.execute(
                "SELECT COUNT(*) FROM source_use_attestations").fetchone()[0],1)


if __name__ == "__main__":
    unittest.main()
