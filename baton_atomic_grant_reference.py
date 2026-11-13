"""Same-SQLite grant/revocation boundary for PR #95's source-use attestations.

REFERENCE ONLY: a real authenticated Core must supply the issuer and revoker.
The grant table MUST live in the *same* SQLite database as UseClaimLedger.
UseClaimLedger.attest() begins an IMMEDIATE write transaction before invoking
this verifier; revocation uses an IMMEDIATE transaction in the same database.
This serializes the two *local* operations. It does NOT make external effects
atomic, authenticate ChatGPT users, or authorize Forum.add_dependency_use().
"""
import re

from baton_use_claims_reference import ID, PRINCIPAL, VerifiedGrant

SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class SameDatabaseGrantAuthority:
    def __init__(self, forum, *, issuer=None, revoker=None):
        self.forum = forum
        self.issuer = issuer
        self.revoker = revoker

    def setup(self):
        with self.forum.connect() as c:
            c.executescript("""
                CREATE TABLE IF NOT EXISTS source_use_grants (
                    grant_id TEXT PRIMARY KEY,
                    principal_id TEXT NOT NULL,
                    scope_digest TEXT NOT NULL,
                    grant_epoch INTEGER NOT NULL CHECK(grant_epoch >= 1),
                    issue_action_id TEXT NOT NULL UNIQUE,
                    revoked INTEGER NOT NULL DEFAULT 0 CHECK(revoked IN (0,1))
                );
            """)

    @staticmethod
    def _id(value):
        if not isinstance(value, str) or not ID.fullmatch(value):
            raise ValueError("invalid grant/action ID")
        return value

    def issue(self, *, grant_id, principal_id, scope_digest, grant_epoch,
              issue_action_id, evidence):
        """A trusted Core issuer authorizes issuance; caller text is not proof."""
        self._id(grant_id)
        self._id(issue_action_id)
        if not isinstance(principal_id, str) or not PRINCIPAL.fullmatch(principal_id):
            raise ValueError("invalid provider-scoped principal")
        if not isinstance(scope_digest, str) or not SHA256.fullmatch(scope_digest):
            raise ValueError("invalid scope digest")
        if type(grant_epoch) is not int or grant_epoch < 1:
            raise ValueError("invalid grant epoch")
        if self.issuer is None:
            raise PermissionError("trusted grant issuer required")
        claim = dict(grant_id=grant_id, principal_id=principal_id,
                     scope_digest=scope_digest, grant_epoch=grant_epoch,
                     issue_action_id=issue_action_id)
        with self.forum.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            if self.issuer(claim, evidence) is not True:
                raise PermissionError("grant issuance not authorized")
            try:
                c.execute("""INSERT INTO source_use_grants
                    (grant_id,principal_id,scope_digest,grant_epoch,issue_action_id)
                    VALUES (?,?,?,?,?)""",
                    (grant_id,principal_id,scope_digest,grant_epoch,issue_action_id))
            except Exception:
                # Duplicate grant IDs cannot be silently renewed or re-scoped.
                raise
        return grant_id

    def revoke(self, grant_id, *, evidence):
        """Revocation and attestation serialize on the same SQLite write lock."""
        self._id(grant_id)
        if self.revoker is None:
            raise PermissionError("trusted grant revoker required")
        with self.forum.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            row = c.execute("""SELECT principal_id,scope_digest,grant_epoch,revoked
                               FROM source_use_grants WHERE grant_id=?""",
                            (grant_id,)).fetchone()
            if row is None:
                raise ValueError("unknown grant")
            if self.revoker({"grant_id":grant_id, "principal_id":row[0],
                             "scope_digest":row[1], "grant_epoch":row[2],
                             "revoked":bool(row[3])}, evidence) is not True:
                raise PermissionError("revocation not authorized")
            if row[3]:
                return False
            c.execute("UPDATE source_use_grants SET revoked=1 WHERE grant_id=?",
                      (grant_id,))
            return True

    def verify(self, claim, evidence):
        """Pass as UseClaimLedger(..., verifier=authority.verify).

        This must be called INSIDE UseClaimLedger.attest's BEGIN IMMEDIATE.
        A standalone call is only a snapshot, never a permission to act later.
        """
        if not isinstance(claim, dict) or not isinstance(evidence, dict):
            raise PermissionError("invalid attestation evidence")
        gid = evidence.get("grant_id")
        action = evidence.get("action_id")
        epoch = evidence.get("grant_epoch")
        if (not isinstance(gid,str) or not ID.fullmatch(gid)
                or not isinstance(action,str) or not ID.fullmatch(action)
                or type(epoch) is not int or epoch < 1):
            raise PermissionError("invalid attestation evidence")
        with self.forum.connect() as c:
            row = c.execute("""SELECT principal_id,scope_digest,grant_epoch,revoked
                               FROM source_use_grants WHERE grant_id=?""",
                            (gid,)).fetchone()
        if (row is None or row[3] or row[2] != epoch
                or row[1] != claim.get("scope_digest")):
            raise PermissionError("revoked, stale or out-of-scope grant")
        return VerifiedGrant(principal_id=row[0],grant_id=gid,
                             grant_epoch=epoch,action_id=action,
                             scope_digest=row[1])

    def attestation_status(self, attestation_id):
        """Historical attestation is never erased by a later revocation."""
        if type(attestation_id) is not int or attestation_id < 1:
            raise ValueError("invalid attestation ID")
        with self.forum.connect() as c:
            row = c.execute("""SELECT a.attestation_id,a.principal_id,a.grant_epoch,
                                      a.scope_digest,g.revoked,g.scope_digest,
                                      g.grant_epoch
                               FROM source_use_attestations a
                               LEFT JOIN source_use_grants g ON g.grant_id=a.grant_id
                               WHERE a.attestation_id=?""",
                            (attestation_id,)).fetchone()
        if row is None:
            return None
        return {"historically_attested":True,
                "currently_unrevoked": bool(row[4] == 0 and row[3] == row[5]
                                            and row[2] == row[6]),
                "principal_id":row[1], "grant_epoch":row[2]}
