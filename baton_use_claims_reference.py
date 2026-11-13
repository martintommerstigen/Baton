"""Reference-only source-use proposals with separately attested registrations.

An untrusted proposal never reserves a canonical use_key. This module does
NOT authenticate ChatGPT users, mint grants, approve sends, or modify legacy
Forum.add_dependency_use. A production Core must supply a trusted verifier
which checks a live, scoped, unrevoked grant in the same authorization domain.
No verifier means fail closed. No proposal is promoted to an operational use.
"""
from dataclasses import dataclass
from hashlib import sha256
import json
import re
from uuid import uuid4

from baton_forum_reference import PREMISE, USES

ID = re.compile(r"[0-9a-f]{32}\Z")
PRINCIPAL = re.compile(r"[a-z][a-z0-9_-]{0,31}:[A-Za-z0-9._:-]{1,120}\Z")


def _digest(data):
    return sha256(json.dumps(data, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class VerifiedGrant:
    """Result of a TRUSTED Core verifier, not a user-supplied identity claim."""
    principal_id: str
    grant_id: str
    grant_epoch: int
    action_id: str
    scope_digest: str


class UseClaimLedger:
    def __init__(self, forum, *, verifier=None):
        self.forum = forum
        self.verifier = verifier

    def setup(self):
        with self.forum.connect() as c:
            c.executescript("""
                CREATE TABLE IF NOT EXISTS source_use_proposals(
                    proposal_id TEXT PRIMARY KEY,
                    downstream_id INTEGER NOT NULL REFERENCES observations(observation_id),
                    upstream_id INTEGER NOT NULL REFERENCES observations(observation_id),
                    use_key TEXT NOT NULL,
                    use_mode TEXT NOT NULL,
                    premise_key TEXT NOT NULL,
                    scope_digest TEXT NOT NULL,
                    -- Deliberately no UNIQUE(downstream_id,use_key): proposals
                    -- cannot consume a canonical key before attestation.
                    CHECK(downstream_id != upstream_id)
                );
                CREATE INDEX IF NOT EXISTS source_use_proposals_by_key
                    ON source_use_proposals(downstream_id,use_key);
                CREATE TABLE IF NOT EXISTS source_use_attestations(
                    attestation_id INTEGER PRIMARY KEY,
                    proposal_id TEXT NOT NULL REFERENCES source_use_proposals(proposal_id),
                    principal_id TEXT NOT NULL,
                    grant_id TEXT NOT NULL,
                    grant_epoch INTEGER NOT NULL,
                    action_id TEXT NOT NULL UNIQUE,
                    scope_digest TEXT NOT NULL
                );
            """)

    @staticmethod
    def _source_scope(c, downstream_id, upstream_id, use_key, use_mode, premise_key,
                      proposal_id):
        downstream = c.execute("""SELECT topic_id,source_chat_id,source_message_id,body_sha256
            FROM observations WHERE observation_id=?""", (downstream_id,)).fetchone()
        upstream = c.execute("""SELECT topic_id,source_chat_id,source_message_id,body_sha256
            FROM observations WHERE observation_id=?""", (upstream_id,)).fetchone()
        if downstream is None or upstream is None:
            raise ValueError("source-use endpoints must be observed")
        return _digest({"proposal_id": proposal_id,
                        "downstream_id": downstream_id, "downstream": downstream,
                        "upstream_id": upstream_id, "upstream": upstream,
                        "use_key": use_key, "use_mode": use_mode,
                        "premise_key": premise_key})

    def propose(self, downstream_id, upstream_id, *, use_key, use_mode,
                premise_key, proposal_id=None):
        """Append an untrusted proposal; no ownership or canonical key implied."""
        if (type(downstream_id) is not int or type(upstream_id) is not int
                or downstream_id < 1 or upstream_id < 1 or downstream_id == upstream_id):
            raise ValueError("invalid source-use endpoints")
        if (not isinstance(use_key, str) or not PREMISE.fullmatch(use_key)
                or use_mode not in USES or not isinstance(premise_key, str)
                or not PREMISE.fullmatch(premise_key)):
            raise ValueError("invalid use descriptors")
        proposal_id = uuid4().hex if proposal_id is None else proposal_id
        if not isinstance(proposal_id, str) or not ID.fullmatch(proposal_id):
            raise ValueError("invalid proposal id")
        with self.forum.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            digest = self._source_scope(c, downstream_id, upstream_id, use_key,
                                        use_mode, premise_key, proposal_id)
            old = c.execute("""SELECT downstream_id,upstream_id,use_key,use_mode,
                premise_key,scope_digest FROM source_use_proposals WHERE proposal_id=?""",
                (proposal_id,)).fetchone()
            expected = (downstream_id, upstream_id, use_key, use_mode, premise_key, digest)
            if old:
                if old != expected:
                    raise ValueError("proposal id cannot be reinterpreted")
                return proposal_id
            c.execute("""INSERT INTO source_use_proposals
                (proposal_id,downstream_id,upstream_id,use_key,use_mode,premise_key,scope_digest)
                VALUES(?,?,?,?,?,?,?)""", (proposal_id, *expected))
            return proposal_id

    def attest(self, proposal_id, evidence):
        """Attest only through a trusted verifier; no verifier = no registration.

        The verifier must check the action, source turn, topic, use, principal,
        grant epoch and revocation, not merely a claimed alias or receipt ID.
        Its result is checked and committed under a BEGIN IMMEDIATE lock.
        """
        if self.verifier is None:
            raise PermissionError("trusted Core use-attestation verifier required")
        if not isinstance(proposal_id, str) or not ID.fullmatch(proposal_id):
            raise ValueError("invalid proposal id")
        with self.forum.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            row = c.execute("""SELECT downstream_id,upstream_id,use_key,use_mode,
                premise_key,scope_digest FROM source_use_proposals WHERE proposal_id=?""",
                (proposal_id,)).fetchone()
            if row is None:
                raise ValueError("proposal missing")
            actual = self._source_scope(c, row[0], row[1], row[2], row[3], row[4],
                                        proposal_id)
            if actual != row[5]:
                raise ValueError("source turn changed after proposal")
            claim = {"proposal_id": proposal_id, "downstream_id": row[0],
                     "upstream_id": row[1], "use_key": row[2], "use_mode": row[3],
                     "premise_key": row[4], "scope_digest": row[5]}
            grant = self.verifier(claim, evidence)
            if (not isinstance(grant, VerifiedGrant)
                    or not isinstance(grant.principal_id, str)
                    or not PRINCIPAL.fullmatch(grant.principal_id)
                    or not isinstance(grant.grant_id, str)
                    or not ID.fullmatch(grant.grant_id)
                    or type(grant.grant_epoch) is not int or grant.grant_epoch < 1
                    or not isinstance(grant.action_id, str)
                    or not ID.fullmatch(grant.action_id)
                    or grant.scope_digest != actual):
                raise PermissionError("invalid or out-of-scope verified grant")
            previous = c.execute("""SELECT attestation_id,proposal_id,principal_id,
                grant_id,grant_epoch,scope_digest FROM source_use_attestations
                WHERE action_id=?""", (grant.action_id,)).fetchone()
            expected = (proposal_id, grant.principal_id, grant.grant_id,
                        grant.grant_epoch, actual)
            if previous:
                if previous[1:] != expected:
                    raise ValueError("action replay cannot change its binding")
                return previous[0]
            cur = c.execute("""INSERT INTO source_use_attestations
                (proposal_id,principal_id,grant_id,grant_epoch,action_id,scope_digest)
                VALUES(?,?,?,?,?,?)""",
                (proposal_id, grant.principal_id, grant.grant_id,
                 grant.grant_epoch, grant.action_id, actual))
            return cur.lastrowid

    def list_for_downstream(self, downstream_id):
        """Expose proposals and attested disagreement; never elect a winner."""
        if type(downstream_id) is not int or downstream_id < 1:
            raise ValueError("invalid downstream id")
        with self.forum.connect() as c:
            rows = c.execute("""SELECT p.proposal_id,p.upstream_id,p.use_key,
                p.use_mode,p.premise_key,a.attestation_id,a.principal_id,a.action_id
                FROM source_use_proposals p LEFT JOIN source_use_attestations a
                  ON p.proposal_id=a.proposal_id
                WHERE p.downstream_id=?
                ORDER BY p.use_key,p.proposal_id,a.attestation_id""",
                (downstream_id,)).fetchall()
        groups = {}
        for proposal_id, upstream, key, mode, premise, att_id, principal, action in rows:
            group = groups.setdefault(key, {"use_key": key, "status": "proposed_only",
                                            "canonical_use_id": None, "proposals": []})
            if not group["proposals"] or group["proposals"][-1]["proposal_id"] != proposal_id:
                group["proposals"].append({"proposal_id": proposal_id,
                    "upstream_id": upstream, "use_mode": mode, "premise_key": premise,
                    "attestations": []})
            if att_id is not None:
                group["proposals"][-1]["attestations"].append({
                    "attestation_id": att_id, "principal_id": principal,
                    "action_id": action})
        for group in groups.values():
            active = {(p["upstream_id"],p["use_mode"],p["premise_key"])
                      for p in group["proposals"] if p["attestations"]}
            group["status"] = ("registration_disputed" if len(active)>1 else
                               "attested" if active else "proposed_only")
        return [groups[k] for k in sorted(groups)]
