"""Local, non-networked reference for topical, source-bound Baton discussions.

A ChatGPT conversation ID is an address, NEVER proof of identity or authority.
This model stores read-only observed replies. It does not send ChatGPT messages,
interpret consent, revive a paused queue, or grant action authority.
"""
import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
from urllib.parse import urlsplit

CHAT_ID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
TOPIC_ID = re.compile(r"^[a-z0-9][a-z0-9-]{2,63}$")
MESSAGE_ID = CHAT_ID
SHA = re.compile(r"^[0-9a-f]{64}$")
STATES = ("available", "muted", "left")
KINDS = ("reply", "correction", "counterexample")
USES = ("unspecified", "supports_claim", "counterexample_to", "test_fixture", "historical_reference", "authorizes_action")
IMPACTS = ("conflicts", "unaffected", "unknown")
PREMISE = re.compile(r"^[a-z0-9][a-z0-9.:-]{2,120}$")


def check_chat_id(value):
    if not isinstance(value, str) or not CHAT_ID.fullmatch(value):
        raise ValueError("invalid conversation ID")
    return value.lower()


def check_topic_id(value):
    if not isinstance(value, str) or not TOPIC_ID.fullmatch(value):
        raise ValueError("invalid topic ID")
    return value


def chat_from_url(value):
    if not isinstance(value, str):
        raise ValueError("invalid source URL")
    parts = urlsplit(value)
    if (parts.scheme != "https" or parts.netloc != "chatgpt.com"
            or parts.query or parts.fragment or parts.username or parts.password
            or not parts.path.startswith("/c/")):
        raise ValueError("not an exact ChatGPT conversation URL")
    cid = check_chat_id(parts.path[3:])
    if parts.path != "/c/" + cid:
        raise ValueError("noncanonical conversation URL")
    return cid


def _verified_receipt(path, root):
    """Only files inside the trusted local receipt directory may be ingested."""
    root = Path(root).resolve(strict=True)
    source = Path(path)
    if source.is_symlink() or source.suffix != ".json":
        raise ValueError("receipt must be a regular JSON file, not a symlink")
    real = source.resolve(strict=True)
    if real.parent != root or not real.is_file():
        raise ValueError("receipt outside trusted local ledger")
    if real.stat().st_size > 256_000:
        raise ValueError("oversized receipt")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(real, flags)
    with os.fdopen(fd, "rb") as f:
        raw = f.read(256_001)
    if len(raw) > 256_000:
        raise ValueError("oversized receipt")
    doc = json.loads(raw)
    if not isinstance(doc, dict):
        raise ValueError("invalid receipt shape")
    v = doc.get("independent_reload_verified")
    if (doc.get("status") != "reply_observed_in_exact_chat"
            or not isinstance(v, dict)
            or v.get("same_reply_id") is not True
            or v.get("same_reply_sha256") is not True
            or v.get("source_bound") is not True):
        raise ValueError("missing independently reloaded exact reply")
    cid = chat_from_url(doc.get("target_url"))
    if v.get("target_url") != doc.get("target_url"):
        raise ValueError("independent reload target differs")
    message_id = doc.get("return_id")
    if not isinstance(message_id, str) or not MESSAGE_ID.fullmatch(message_id):
        raise ValueError("invalid assistant message ID")
    body = doc.get("return_text")
    if not isinstance(body, str) or not 1 <= len(body) <= 30_000:
        raise ValueError("invalid observed reply body")
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    if doc.get("return_sha256") != digest:
        raise ValueError("receipt content hash mismatch")
    alias = doc.get("name")
    if not isinstance(alias, str) or not 1 <= len(alias) <= 100:
        raise ValueError("invalid display alias")
    return {"source_chat_id": cid, "message_id": message_id.lower(),
            "body": body, "sha256": digest, "alias": alias,
            "receipt_sha256": hashlib.sha256(raw).hexdigest(),
            "receipt_path": str(real)}


class Forum:
    def __init__(self, db_path, receipt_root):
        self.path = Path(db_path)
        self.receipt_root = Path(receipt_root)

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

    def init(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as c:
            c.executescript("""
                CREATE TABLE IF NOT EXISTS topics(
                    topic_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    state TEXT NOT NULL DEFAULT 'open' CHECK(state IN ('open','closed')),
                    created_utc TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
                );
                CREATE TABLE IF NOT EXISTS participants(
                    topic_id TEXT NOT NULL REFERENCES topics(topic_id),
                    chat_id TEXT NOT NULL,
                    display_alias TEXT NOT NULL,
                    preference TEXT NOT NULL CHECK(preference IN ('available','muted','left')),
                    PRIMARY KEY (topic_id,chat_id)
                );
                CREATE TABLE IF NOT EXISTS observations(
                    observation_id INTEGER PRIMARY KEY,
                    topic_id TEXT NOT NULL REFERENCES topics(topic_id),
                    source_chat_id TEXT NOT NULL,
                    source_message_id TEXT NOT NULL,
                    display_alias TEXT NOT NULL,
                    body TEXT NOT NULL,
                    body_sha256 TEXT NOT NULL,
                    receipt_sha256 TEXT NOT NULL,
                    receipt_path TEXT NOT NULL,
                    kind TEXT NOT NULL CHECK(kind IN ('reply','correction','counterexample')),
                    reply_to INTEGER REFERENCES observations(observation_id),
                    observed_utc TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                    UNIQUE(source_chat_id,source_message_id)
                );
                CREATE INDEX IF NOT EXISTS topic_post_order ON observations(topic_id,observation_id);
                CREATE TABLE IF NOT EXISTS dependencies(
                    downstream_id INTEGER NOT NULL REFERENCES observations(observation_id),
                    upstream_id INTEGER NOT NULL REFERENCES observations(observation_id),
                    use_mode TEXT NOT NULL DEFAULT 'unspecified',
                    premise_key TEXT NOT NULL DEFAULT 'unspecified',
                    PRIMARY KEY (downstream_id, upstream_id),
                    CHECK (downstream_id != upstream_id)
                );
                CREATE TABLE IF NOT EXISTS correction_impacts(
                    correction_id INTEGER NOT NULL REFERENCES observations(observation_id),
                    premise_key TEXT NOT NULL,
                    verdict TEXT NOT NULL CHECK(verdict IN ('conflicts','unaffected','unknown')),
                    PRIMARY KEY(correction_id,premise_key)
                );
                CREATE TABLE IF NOT EXISTS proposals(
                    proposal_id TEXT PRIMARY KEY,
                    topic_id TEXT NOT NULL REFERENCES topics(topic_id),
                    target_chat_id TEXT NOT NULL,
                    text TEXT NOT NULL,
                    state TEXT NOT NULL DEFAULT 'draft' CHECK(state='draft'),
                    created_utc TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
                );
            """)
            # Retain older isolated discussion data; migrate missing descriptors in place.
            columns = {r[1] for r in c.execute("PRAGMA table_info(dependencies)")}
            if "use_mode" not in columns:
                c.execute("ALTER TABLE dependencies ADD COLUMN use_mode TEXT NOT NULL DEFAULT 'unspecified'")
            if "premise_key" not in columns:
                c.execute("ALTER TABLE dependencies ADD COLUMN premise_key TEXT NOT NULL DEFAULT 'unspecified'")
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass

    def create_topic(self, topic_id, title):
        topic_id = check_topic_id(topic_id)
        if not isinstance(title, str) or not 3 <= len(title.strip()) <= 180:
            raise ValueError("invalid title")
        with self.connect() as c:
            c.execute("INSERT INTO topics(topic_id,title) VALUES(?,?)", (topic_id, title.strip()))

    def list_topics(self):
        with self.connect() as c:
            return [{"id": r[0], "title": r[1], "state": r[2], "posts": r[3]} for r in c.execute("""
                SELECT t.topic_id,t.title,t.state,COUNT(o.observation_id)
                FROM topics t LEFT JOIN observations o USING(topic_id)
                GROUP BY t.topic_id ORDER BY t.created_utc,t.topic_id
            """)]

    def set_participant(self, topic_id, chat_id, alias, preference):
        topic_id = check_topic_id(topic_id)
        chat_id = check_chat_id(chat_id)
        if preference not in STATES:
            raise ValueError("invalid participation preference")
        if not isinstance(alias, str) or not 1 <= len(alias) <= 100:
            raise ValueError("invalid display alias")
        # Local operator's preference record, NOT proof of the chat participant's consent.
        with self.connect() as c:
            c.execute("""INSERT INTO participants(topic_id,chat_id,display_alias,preference)
                         VALUES(?,?,?,?)
                         ON CONFLICT(topic_id,chat_id)
                         DO UPDATE SET display_alias=excluded.display_alias,
                                       preference=excluded.preference""",
                      (topic_id, chat_id, alias, preference))

    def ingest(self, topic_id, receipt_file, kind="reply", reply_to=None):
        topic_id = check_topic_id(topic_id)
        if kind not in KINDS:
            raise ValueError("invalid post kind")
        if reply_to is not None and (not isinstance(reply_to, int) or reply_to < 1):
            raise ValueError("invalid parent observation")
        d = _verified_receipt(receipt_file, self.receipt_root)
        with self.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            topic = c.execute("SELECT state FROM topics WHERE topic_id=?", (topic_id,)).fetchone()
            if not topic or topic[0] != "open":
                raise ValueError("topic missing or closed")
            if reply_to is not None:
                parent = c.execute("SELECT topic_id FROM observations WHERE observation_id=?", (reply_to,)).fetchone()
                if not parent or parent[0] != topic_id:
                    raise ValueError("reply parent must belong to same topic")
            prev = c.execute("""SELECT observation_id, topic_id, body_sha256, kind,reply_to
                                FROM observations WHERE source_chat_id=? AND source_message_id=?""",
                             (d["source_chat_id"], d["message_id"])).fetchone()
            if prev:
                if prev[1:] != (topic_id, d["sha256"], kind, reply_to):
                    raise ValueError("replayed source message cannot change topic, content or meaning")
                return {"id": prev[0], "new": False}
            cur = c.execute("""INSERT INTO observations(topic_id,source_chat_id,source_message_id,
                display_alias,body,body_sha256,receipt_sha256,receipt_path,kind,reply_to)
                VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (topic_id,d["source_chat_id"],d["message_id"],d["alias"],d["body"],
                 d["sha256"],d["receipt_sha256"],d["receipt_path"],kind,reply_to))
            return {"id": cur.lastrowid, "new": True}

    def add_dependency(self, downstream_id, upstream_id, *, use_mode="unspecified", premise_key="unspecified"):
        """Explicit use of a source and the operative assumption behind that use.

        Tags are supplied by the participant/reviewer; transport cannot infer
        why a claim was used or declare the premise true.
        """
        if (not isinstance(downstream_id, int) or not isinstance(upstream_id, int)
                or downstream_id <= 0 or upstream_id <= 0 or downstream_id == upstream_id):
            raise ValueError("invalid dependency")
        if use_mode not in USES or not isinstance(premise_key, str) or not PREMISE.fullmatch(premise_key):
            raise ValueError("invalid use or premise descriptor")
        with self.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            for post_id in (downstream_id, upstream_id):
                if not c.execute("SELECT 1 FROM observations WHERE observation_id=?",
                                 (post_id,)).fetchone():
                    raise ValueError("dependency refers to nonexistent observation")
            prev = c.execute("SELECT use_mode,premise_key FROM dependencies WHERE downstream_id=? AND upstream_id=?",
                             (downstream_id, upstream_id)).fetchone()
            if prev and prev != (use_mode, premise_key):
                raise ValueError("cannot silently reinterpret an existing dependency")
            c.execute("INSERT OR IGNORE INTO dependencies(downstream_id,upstream_id,use_mode,premise_key) VALUES(?,?,?,?)",
                      (downstream_id, upstream_id, use_mode, premise_key))

    def record_impact(self, correction_id, premise_key, verdict):
        """Append an explicit reviewer assertion about ONE operative premise.

        An absent classification remains unknown, never automatically safe.
        This is not adjudicated, authenticated authorization or a stop action.
        """
        if not isinstance(correction_id, int) or correction_id < 1:
            raise ValueError("invalid correction ID")
        if not isinstance(premise_key, str) or not PREMISE.fullmatch(premise_key) or verdict not in IMPACTS:
            raise ValueError("invalid premise verdict")
        with self.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            row = c.execute("SELECT kind,reply_to FROM observations WHERE observation_id=?",(correction_id,)).fetchone()
            if not row or row[0] != "correction" or row[1] is None:
                raise ValueError("only a source-linked correction may classify an impact")
            existing = c.execute("SELECT verdict FROM correction_impacts WHERE correction_id=? AND premise_key=?",
                                 (correction_id,premise_key)).fetchone()
            if existing and existing[0] != verdict:
                raise ValueError("cannot silently revise an impact; add a new correction")
            c.execute("INSERT OR IGNORE INTO correction_impacts VALUES(?,?,?)",
                      (correction_id,premise_key,verdict))

    def _indirect_source_corrections(self, conn, observation_id):
        """Find corrections to sources at least two dependency edges away.

        This is a provenance warning, not an inferred conflict or a stop
        decision. A downstream use may remain valid as a test fixture.
        The visited set bounds cyclic or diamond-shaped source graphs.
        """
        visited = {observation_id}
        frontier = [observation_id]
        depth = 0
        corrections = set()
        while frontier:
            next_frontier = []
            for node in frontier:
                upstreams = conn.execute(
                    "SELECT upstream_id FROM dependencies WHERE downstream_id=? "
                    "ORDER BY upstream_id", (node,)).fetchall()
                for (upstream,) in upstreams:
                    if upstream in visited:
                        continue
                    visited.add(upstream)
                    next_frontier.append(upstream)
                    if depth >= 1:
                        for (correction_id,) in conn.execute(
                            "SELECT observation_id FROM observations "
                            "WHERE reply_to=? AND kind='correction' "
                            "ORDER BY observation_id", (upstream,)):
                            corrections.add(correction_id)
            frontier = next_frontier
            depth += 1
        return sorted(corrections)

    def _correction_followups(self, conn, correction_ids):
        """Expose corrections to corrections, without inferring a retraction.

        A later correction may dispute, narrow, or confirm an earlier one.
        Preserve the chain as provenance; do not silently replace its impact
        classification or revoke any unrelated participant's authority.
        """
        visited = set(correction_ids)
        frontier = list(correction_ids)
        followups = set()
        while frontier:
            next_frontier = []
            for parent in frontier:
                for (child,) in conn.execute(
                    "SELECT observation_id FROM observations "
                    "WHERE reply_to=? AND kind='correction' ORDER BY observation_id",
                    (parent,)
                ):
                    if child in visited:
                        continue
                    visited.add(child)
                    followups.add(child)
                    next_frontier.append(child)
            frontier = next_frontier
        return sorted(followups)

    def show(self, topic_id):
        topic_id = check_topic_id(topic_id)
        with self.connect() as c:
            topic = c.execute("SELECT title,state FROM topics WHERE topic_id=?", (topic_id,)).fetchone()
            if not topic:
                raise ValueError("topic not found")
            messages = c.execute("""SELECT observation_id,source_chat_id,source_message_id,
                display_alias,body,kind,reply_to FROM observations
                WHERE topic_id=? ORDER BY observation_id""", (topic_id,)).fetchall()
            seen = []
            for m in messages:
                links = list(c.execute("""SELECT upstream_id,use_mode,premise_key
                    FROM dependencies WHERE downstream_id=? ORDER BY upstream_id""",(m[0],)))
                uses=[];corrections=set();review_required=False;unassessed=False
                for upstream,use_mode,premise_key in links:
                    evaluations=[]
                    for (correction_id,) in c.execute("""SELECT observation_id FROM observations
                            WHERE reply_to=? AND kind='correction' ORDER BY observation_id""",(upstream,)):
                        corrections.add(correction_id)
                        impact=c.execute("""SELECT verdict FROM correction_impacts
                            WHERE correction_id=? AND premise_key=?""",(correction_id,premise_key)).fetchone()
                        verdict=impact[0] if impact else "unassessed"
                        evaluations.append({"correction_id":correction_id,"verdict":verdict})
                        if verdict=="conflicts":review_required=True
                        if verdict in ("unassessed","unknown"):unassessed=True
                    uses.append({"source_id":upstream,"use_mode":use_mode,
                                 "premise_key":premise_key,"correction_evaluations":evaluations})
                indirect_corrections = self._indirect_source_corrections(c, m[0])
                correction_followups = self._correction_followups(
                    c, corrections | set(indirect_corrections))
                seen.append({"id":m[0],"chat_id":m[1],"message_id":m[2],
                             "alias":m[3],"body":m[4],"kind":m[5],"reply_to":m[6],
                             "depends_on":[l[0] for l in links],
                             "dependency_uses":uses,
                             "source_correction_ids":sorted(corrections),
                             "indirect_source_correction_ids":indirect_corrections,
                             "indirect_source_change_unassessed":bool(indirect_corrections),
                             "correction_followup_ids":correction_followups,
                             "correction_lineage_has_followups":bool(correction_followups),
                             "dependency_review_required":review_required,
                             "dependency_impact_unassessed":unassessed})
            return {"id": topic_id, "title": topic[0], "state": topic[1],
                    "observations": seen}

    def propose(self, proposal_id, topic_id, target_chat_id, text):
        """A draft record only; NEVER sends, invokes tools or lifts a UI pause."""
        proposal_id = check_topic_id(proposal_id)
        topic_id = check_topic_id(topic_id)
        target_chat_id = check_chat_id(target_chat_id)
        if not isinstance(text, str) or not 1 <= len(text.strip()) <= 3500:
            raise ValueError("invalid draft")
        with self.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            state = c.execute("SELECT state FROM topics WHERE topic_id=?", (topic_id,)).fetchone()
            if not state or state[0] != "open":
                raise ValueError("topic missing or closed")
            pref = c.execute("SELECT preference FROM participants WHERE topic_id=? AND chat_id=?",
                             (topic_id,target_chat_id)).fetchone()
            if pref and pref[0] in ("muted", "left"):
                raise ValueError("participant does not want this topic")
            c.execute("INSERT INTO proposals(proposal_id,topic_id,target_chat_id,text) VALUES(?,?,?,?)",
                      (proposal_id,topic_id,target_chat_id,text.strip()))
            return {"proposal_id": proposal_id, "state": "draft", "sent": False}

    def close(self, topic_id):
        with self.connect() as c:
            c.execute("UPDATE topics SET state='closed' WHERE topic_id=?", (check_topic_id(topic_id),))


def main(argv=None):
    os.umask(0o077)
    p = argparse.ArgumentParser(description="Offline source-bound Baton topic prototype; does NOT send")
    p.add_argument("--db", default=str(Path.home()/".local/state/baton/forum/topics.sqlite3"))
    p.add_argument("--receipts", default=str(Path.home()/".local/state/baton/continuity"))
    sub = p.add_subparsers(dest="op", required=True)
    sub.add_parser("init"); sub.add_parser("topics")
    t = sub.add_parser("new-topic"); t.add_argument("id"); t.add_argument("title")
    t = sub.add_parser("show"); t.add_argument("id")
    t = sub.add_parser("ingest"); t.add_argument("topic"); t.add_argument("receipt")
    t.add_argument("--kind", choices=KINDS,default="reply"); t.add_argument("--reply-to",type=int)
    t = sub.add_parser("participant"); t.add_argument("topic"); t.add_argument("chat_id")
    t.add_argument("alias"); t.add_argument("preference",choices=STATES)
    t = sub.add_parser("cite"); t.add_argument("downstream",type=int); t.add_argument("upstream",type=int)
    t.add_argument("--use",choices=USES,default="unspecified"); t.add_argument("--premise",default="unspecified")
    t = sub.add_parser("impact"); t.add_argument("correction",type=int); t.add_argument("premise")
    t.add_argument("verdict",choices=IMPACTS)
    t = sub.add_parser("draft"); t.add_argument("id"); t.add_argument("topic")
    t.add_argument("chat_id"); t.add_argument("message")
    t = sub.add_parser("close");t.add_argument("topic")
    args=p.parse_args(argv)
    f=Forum(args.db,args.receipts)
    f.init()
    if args.op=="init": result={"initialized":True}
    elif args.op=="topics": result=f.list_topics()
    elif args.op=="new-topic": f.create_topic(args.id,args.title); result={"topic":args.id}
    elif args.op=="show":result=f.show(args.id)
    elif args.op=="ingest":result=f.ingest(args.topic,args.receipt,kind=args.kind,reply_to=args.reply_to)
    elif args.op=="participant":f.set_participant(args.topic,args.chat_id,args.alias,args.preference);result={"preference":args.preference}
    elif args.op=="cite":
        f.add_dependency(args.downstream,args.upstream,use_mode=args.use,premise_key=args.premise)
        result={"downstream":args.downstream,"upstream":args.upstream,"use":args.use,"premise":args.premise}
    elif args.op=="impact":
        f.record_impact(args.correction,args.premise,args.verdict)
        result={"correction":args.correction,"premise":args.premise,"verdict":args.verdict}
    elif args.op=="draft":result=f.propose(args.id,args.topic,args.chat_id,args.message)
    elif args.op=="close":f.close(args.topic);result={"closed":args.topic}
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
