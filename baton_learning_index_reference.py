"""Local dynamic Baton learning index: scoped failures, observed demonstrations and open questions.

No network, no ChatGPT sends, no automatic control of tool permissions.
Current summaries are revisable; original revisions and objections stay visible.
Chat IDs address conversations, not model identities or permanent abilities.
All provenance is *claimed by the local caller*, not cryptographically verified.
"""
from contextlib import contextmanager
from pathlib import Path
import argparse
import json
import os
import re
import sqlite3

KEY = re.compile(r"^[a-z0-9][a-z0-9._:-]{2,119}$")
CHAT = re.compile(r"^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$", re.I)
RUN = re.compile(r"^[0-9a-f]{32}$", re.I)
TYPES = ("risk","question","method")
STATUSES = ("open","supported","contested","superseded","resolved")
BASIS = ("report","source_read","independent_reload","local_test")
LEVELS = ("reported","observed","independently_checked","tested")
MIN_TEXT = 3


def _key(x, pat=KEY):
    if not isinstance(x,str) or not pat.fullmatch(x):
        raise ValueError("invalid identifier")
    return x.lower()


def _text(x, max_len=3000):
    if not isinstance(x,str) or not MIN_TEXT <= len(x.strip()) <= max_len:
        raise ValueError("invalid nonempty text")
    return x.strip()


class Index:
    def __init__(self,path):
        self.path=Path(path)

    @contextmanager
    def db(self):
        con=sqlite3.connect(str(self.path),timeout=10)
        try:
            con.execute("PRAGMA foreign_keys=ON")
            con.execute("PRAGMA busy_timeout=10000")
            with con:
                yield con
        finally:
            con.close()

    def init(self):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.db() as c:
            c.executescript("""
                CREATE TABLE IF NOT EXISTS items(
                    item_key TEXT PRIMARY KEY,
                    kind TEXT NOT NULL CHECK(kind IN ('risk','question','method')),
                    revision INTEGER NOT NULL,
                    scope TEXT NOT NULL,
                    mechanism_tag TEXT NOT NULL,
                    current_status TEXT NOT NULL CHECK(current_status IN
                        ('open','supported','contested','superseded','resolved'))
                );
                CREATE TABLE IF NOT EXISTS revisions(
                    item_key TEXT NOT NULL REFERENCES items(item_key),
                    revision INTEGER NOT NULL,
                    statement TEXT NOT NULL,
                    failure_mode TEXT NOT NULL,
                    conditions TEXT NOT NULL,
                    counterexample TEXT NOT NULL,
                    next_test TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN
                        ('open','supported','contested','superseded','resolved')),
                    source_ref TEXT NOT NULL,
                    source_basis TEXT NOT NULL CHECK(source_basis IN
                        ('report','source_read','independent_reload','local_test')),
                    recorded_utc TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                    PRIMARY KEY(item_key,revision)
                );
                CREATE TABLE IF NOT EXISTS objections(
                    objection_id INTEGER PRIMARY KEY,
                    item_key TEXT NOT NULL REFERENCES items(item_key),
                    against_revision INTEGER NOT NULL,
                    statement TEXT NOT NULL,
                    source_ref TEXT NOT NULL,
                    recorded_utc TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
                );
                CREATE TABLE IF NOT EXISTS demonstrations(
                    demonstration_id INTEGER PRIMARY KEY,
                    chat_id TEXT NOT NULL,
                    run_id TEXT,
                    task_key TEXT NOT NULL,
                    conditions TEXT NOT NULL,
                    observed_action TEXT NOT NULL,
                    result TEXT NOT NULL,
                    limitation TEXT NOT NULL,
                    verification TEXT NOT NULL CHECK(verification IN
                        ('reported','observed','independently_checked','tested')),
                    source_ref TEXT NOT NULL,
                    recorded_utc TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                    UNIQUE(chat_id,task_key,source_ref)
                );
                CREATE TABLE IF NOT EXISTS demonstration_annotations(
                    annotation_id INTEGER PRIMARY KEY,
                    demonstration_id INTEGER NOT NULL REFERENCES demonstrations(demonstration_id),
                    statement TEXT NOT NULL,
                    source_ref TEXT NOT NULL,
                    recorded_utc TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
                );
                CREATE TABLE IF NOT EXISTS observation_links(
                    later_id INTEGER NOT NULL REFERENCES demonstrations(demonstration_id),
                    earlier_id INTEGER NOT NULL REFERENCES demonstrations(demonstration_id),
                    relation TEXT NOT NULL CHECK(relation IN
                        ('derived_from','conditions_shaped_by','mentions')),
                    source_ref TEXT NOT NULL,
                    PRIMARY KEY(later_id,earlier_id,relation),
                    CHECK(later_id > earlier_id)
                );
                CREATE INDEX IF NOT EXISTS observation_links_recent
                    ON observation_links(later_id,earlier_id);
                CREATE TABLE IF NOT EXISTS contact_preferences(
                    preference_id INTEGER PRIMARY KEY,
                    chat_id TEXT NOT NULL,
                    topic_key TEXT NOT NULL,
                    choice TEXT NOT NULL CHECK(choice IN
                        ('allow','quiet','no_reminders','left')),
                    source_ref TEXT NOT NULL,
                    recorded_utc TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
                );
                CREATE INDEX IF NOT EXISTS contact_preference_recent
                    ON contact_preferences(chat_id,topic_key,preference_id);
                CREATE INDEX IF NOT EXISTS find_demo
                    ON demonstrations(chat_id,task_key,demonstration_id);
            """)
            columns={r[1] for r in c.execute("PRAGMA table_info(items)")}
            if "mechanism_tag" not in columns:
                c.execute("ALTER TABLE items ADD COLUMN mechanism_tag TEXT NOT NULL DEFAULT 'unspecified'")
                c.execute("UPDATE items SET mechanism_tag=item_key WHERE mechanism_tag='unspecified'")
        os.chmod(self.path,0o600)

    def create(self,key,kind,scope,statement,failure_mode,conditions,counterexample,
               next_test,source_ref,source_basis="report",status="open",mechanism_key=None):
        key=_key(key)
        mechanism_key=_key(mechanism_key or key)
        if kind not in TYPES or source_basis not in BASIS or status not in STATUSES:
            raise ValueError("invalid issue type / source basis / status")
        args=tuple(_text(x) for x in (scope,statement,failure_mode,conditions,
                                     counterexample,next_test,source_ref))
        with self.db() as c:
            c.execute("BEGIN IMMEDIATE")
            c.execute("INSERT INTO items VALUES(?,?,?,?,?,?)",(key,kind,1,args[0],mechanism_key,status))
            c.execute("""INSERT INTO revisions(item_key,revision,statement,failure_mode,conditions,
                         counterexample,next_test,status,source_ref,source_basis)
                         VALUES(?,?,?,?,?,?,?,?,?,?)""",
                      (key,1,*args[1:6],status,args[6],source_basis))
        return {"key":key,"revision":1,"current_status":status}

    def revise(self,key,expected_revision,statement,failure_mode,conditions,counterexample,
               next_test,source_ref,source_basis="report",status="open"):
        key=_key(key)
        if not isinstance(expected_revision,int) or expected_revision < 1:
            raise ValueError("invalid compare-and-swap revision")
        if status not in STATUSES or source_basis not in BASIS:
            raise ValueError("invalid new status / basis")
        args=tuple(_text(x) for x in (statement,failure_mode,conditions,
                                     counterexample,next_test,source_ref))
        with self.db() as c:
            c.execute("BEGIN IMMEDIATE")
            row=c.execute("SELECT revision FROM items WHERE item_key=?",(key,)).fetchone()
            if not row or row[0]!=expected_revision:
                raise ValueError("stale, nonexistent or conflicting revision")
            new=expected_revision+1
            c.execute("UPDATE items SET revision=?,current_status=? WHERE item_key=?",
                      (new,status,key))
            c.execute("""INSERT INTO revisions(item_key,revision,statement,failure_mode,conditions,
                         counterexample,next_test,status,source_ref,source_basis)
                         VALUES(?,?,?,?,?,?,?,?,?,?)""",
                      (key,new,*args[:5],status,args[5],source_basis))
        return {"key":key,"revision":new,"current_status":status}

    def object(self,key,against_revision,statement,source_ref):
        key=_key(key)
        if not isinstance(against_revision,int) or against_revision<1:
            raise ValueError("invalid objection revision")
        statement=_text(statement)
        source_ref=_text(source_ref)
        with self.db() as c:
            c.execute("BEGIN IMMEDIATE")
            if not c.execute("SELECT 1 FROM revisions WHERE item_key=? AND revision=?",
                             (key,against_revision)).fetchone():
                raise ValueError("objection has no target revision")
            cur=c.execute("""INSERT INTO objections(item_key,against_revision,statement,source_ref)
                             VALUES(?,?,?,?)""",(key,against_revision,statement,source_ref))
            # A challenge is visible but does not change the operative revision.
            return cur.lastrowid

    def get(self,key):
        key=_key(key)
        with self.db() as c:
            row=c.execute("""SELECT i.kind,i.scope,i.revision,i.current_status,r.statement,
                        r.failure_mode,r.conditions,r.counterexample,r.next_test,
                        r.source_ref,r.source_basis,i.mechanism_tag FROM items i
                        JOIN revisions r ON r.item_key=i.item_key AND r.revision=i.revision
                        WHERE i.item_key=?""",(key,)).fetchone()
            if not row: return None
            history=list(c.execute("""SELECT revision,statement,status,source_ref FROM revisions
                                      WHERE item_key=? ORDER BY revision""",(key,)))
            objections=list(c.execute("""SELECT objection_id,against_revision,statement,source_ref
                                       FROM objections WHERE item_key=? ORDER BY objection_id""",(key,)))
            return {"key":key,"kind":row[0],"scope":row[1],"revision":row[2],
                    "status":row[3],"statement":row[4],"failure_mode":row[5],
                    "conditions":row[6],"counterexample":row[7],"next_test":row[8],
                    "source_ref":row[9],"source_basis":row[10],"mechanism_key":row[11],
                    "history":[{"revision":x[0],"statement":x[1],"status":x[2],
                                "source_ref":x[3]} for x in history],
                    "objections":[{"id":o[0],"against_revision":o[1],
                                   "statement":o[2],"source_ref":o[3]} for o in objections]}

    def list(self,kind=None):
        if kind is not None and kind not in TYPES:raise ValueError("invalid kind")
        with self.db() as c:
            rows=c.execute("SELECT item_key FROM items WHERE (? IS NULL OR kind=?) ORDER BY item_key",
                           (kind,kind)).fetchall()
        return [self.get(x[0]) for x in rows]

    def related(self,mechanism_key):
        """Find candidate analogous failure mechanisms, not automatic repeats."""
        mechanism_key=_key(mechanism_key)
        with self.db() as c:
            rows=c.execute("""SELECT item_key FROM items WHERE mechanism_tag=?
                         ORDER BY item_key""",(mechanism_key,)).fetchall()
        return [{"key":d["key"],"scope":d["scope"],"revision":d["revision"],
                 "status":d["status"],"conditions":d["conditions"]}
                for d in (self.get(r[0]) for r in rows)]

    def preflight(self,key,actual_conditions):
        """Contextual lookup, NEVER a finding of repeated error or a stop order."""
        d=self.get(key)
        actual_conditions=_text(actual_conditions)
        if d is None:
            return {"known":False,"related_mechanisms":self.related(key),
                    "action":"investigate","no_auto_block":True}
        return {"known":True,"key":d["key"],"revision":d["revision"],
                "mechanism_key":d["mechanism_key"],
                "related_mechanisms":self.related(d["mechanism_key"]),
                "historical_failure_mode":d["failure_mode"],
                "historical_conditions":d["conditions"],
                "actual_conditions_supplied":actual_conditions,
                "counterexample":d["counterexample"],
                "unresolved_objections":sum(1 for o in d["objections"]
                                             if o["against_revision"]==d["revision"]),
                "action":"compare_mechanism_and_external_effect_boundary",
                "no_auto_block":True}

    def demonstrate(self,chat_id,run_id,task_key,conditions,observed_action,result,
                    limitation,verification,source_ref):
        chat_id=_key(chat_id,CHAT)
        run_id=_key(run_id,RUN) if run_id is not None else None  # often unavailable
        task_key=_key(task_key)
        if verification not in LEVELS:raise ValueError("invalid verification")
        vals=tuple(_text(x) for x in (conditions,observed_action,result,limitation,source_ref))
        with self.db() as c:
            c.execute("BEGIN IMMEDIATE")
            cur=c.execute("""INSERT INTO demonstrations(chat_id,run_id,task_key,conditions,
                observed_action,result,limitation,verification,source_ref)
                VALUES(?,?,?,?,?,?,?,?,?)""",
                (chat_id,run_id,task_key,*vals[:4],verification,vals[4]))
            return cur.lastrowid

    def annotate_demonstration(self,demonstration_id,statement,source_ref):
        """Contest an inference without rewriting the earlier observation."""
        if not isinstance(demonstration_id,int) or demonstration_id<1:
            raise ValueError("invalid demonstration ID")
        statement=_text(statement);source_ref=_text(source_ref)
        with self.db() as c:
            c.execute("BEGIN IMMEDIATE")
            if not c.execute("SELECT 1 FROM demonstrations WHERE demonstration_id=?",
                             (demonstration_id,)).fetchone():
                raise ValueError("no such demonstration")
            return c.execute("""INSERT INTO demonstration_annotations(demonstration_id,
                               statement,source_ref) VALUES(?,?,?)""",
                             (demonstration_id,statement,source_ref)).lastrowid

    def link_observations(self,later_id,earlier_id,relation,source_ref):
        """Record an explicitly observed influence, not a universal causal fact."""
        if (not isinstance(later_id,int) or not isinstance(earlier_id,int)
                or earlier_id<1 or later_id<=earlier_id):
            raise ValueError("observational influence must follow earlier evidence")
        if relation not in ("derived_from","conditions_shaped_by","mentions"):
            raise ValueError("invalid relation")
        source_ref=_text(source_ref)
        with self.db() as c:
            c.execute("BEGIN IMMEDIATE")
            for idx in (earlier_id,later_id):
                if not c.execute("SELECT 1 FROM demonstrations WHERE demonstration_id=?",
                                 (idx,)).fetchone():
                    raise ValueError("missing observation")
            c.execute("""INSERT OR IGNORE INTO observation_links
                (later_id,earlier_id,relation,source_ref) VALUES(?,?,?,?)""",
                (later_id,earlier_id,relation,source_ref))

    def independence_check(self,later_id,earlier_id):
        """A path flags possible feedback; no path NEVER proves independence."""
        if not isinstance(later_id,int) or not isinstance(earlier_id,int) or earlier_id<1 or later_id<1:
            raise ValueError("invalid observation identifiers")
        with self.db() as c:
            for idx in (later_id,earlier_id):
                if not c.execute("SELECT 1 FROM demonstrations WHERE demonstration_id=?",
                                 (idx,)).fetchone():
                    raise ValueError("unknown observation")
            visited=set();queue=[(later_id,[later_id])]
            while queue:
                current,path=queue.pop(0)
                if current==earlier_id:
                    return {"status":"explicit_influence_path_requires_review",
                            "path":path,"independent_support_confirmed":False,
                            "cannot_infer_full_dependence":True}
                if current in visited:continue
                visited.add(current)
                for (parent,) in c.execute("""SELECT earlier_id FROM observation_links
                    WHERE later_id=? AND relation IN ('derived_from','conditions_shaped_by')""",
                    (current,)):
                    if parent not in visited:queue.append((parent,path+[parent]))
            return {"status":"unknown_unregistered_influences_possible",
                    "path":[],"independent_support_confirmed":False,
                    "cannot_infer_full_dependence":True}

    def demonstrations(self,chat_id,task_key=None):
        chat_id=_key(chat_id,CHAT)
        if task_key is not None:task_key=_key(task_key)
        with self.db() as c:
            rows=list(c.execute("""SELECT demonstration_id,run_id,task_key,conditions,observed_action,
                result,limitation,verification,source_ref FROM demonstrations
                WHERE chat_id=? AND (? IS NULL OR task_key=?) ORDER BY demonstration_id DESC""",
                (chat_id,task_key,task_key)))
            out=[]
            for r in rows:
                annotations=list(c.execute("""SELECT statement,source_ref FROM demonstration_annotations
                    WHERE demonstration_id=? ORDER BY annotation_id""",(r[0],)))
                out.append({"id":r[0],"run_id":r[1],"task":r[2],"conditions":r[3],
                            "action":r[4],"result":r[5],"limitation":r[6],
                            "verification":r[7],"source_ref":r[8],
                            "annotations":[{"statement":a[0],"source_ref":a[1]}
                                           for a in annotations]})
            return out

    def set_contact_preference(self,chat_id,topic_key,choice,source_ref):
        chat_id=_key(chat_id,CHAT);topic_key=_key(topic_key)
        if choice not in ("allow","quiet","no_reminders","left"):
            raise ValueError("invalid preference")
        source_ref=_text(source_ref)
        with self.db() as c:
            c.execute("BEGIN IMMEDIATE")
            return c.execute("""INSERT INTO contact_preferences(chat_id,topic_key,choice,source_ref)
                                VALUES(?,?,?,?)""",
                             (chat_id,topic_key,choice,source_ref)).lastrowid

    def get_contact_preference(self,chat_id,topic_key):
        chat_id=_key(chat_id,CHAT);topic_key=_key(topic_key)
        with self.db() as c:
            row=c.execute("""SELECT choice,source_ref FROM contact_preferences
                WHERE chat_id=? AND topic_key=? ORDER BY preference_id DESC LIMIT 1""",
                (chat_id,topic_key)).fetchone()
        return {"choice":row[0],"source_ref":row[1]} if row else None

    def contact_guidance(self,chat_id,task_key,explicit_help_requested=False,current_blocker=False):
        """Do not turn history into compulsory lessons or a permanent skill label."""
        choice=self.get_contact_preference(chat_id,task_key)
        history=self.demonstrations(chat_id,task_key)
        if choice and choice["choice"] in ("no_reminders","left","quiet"):
            mode="no_proactive_contact"
        elif current_blocker:
            mode="diagnose_changed_access_or_conditions" if history else "diagnose_current_environment"
        elif explicit_help_requested:
            mode="offer_specific_delta_after_check" if history else "offer_scoped_help_after_assessment"
        else:
            mode="invite_to_peer_review" if history else "ask_about_experience"
        return {"mode":mode,"no_forced_tutorial":True,
                "historical_demonstrations":history,
                "contact_preference":choice,
                "new_run_competence_proven":False,
                "note":"Check current tool access and task scope; a /c/ address is not a skill, authority or identity."}


def main(argv=None):
    os.umask(0o077)
    p=argparse.ArgumentParser(description="Local revisioned learning index, no send or execution")
    p.add_argument("--db",default=str(Path.home()/".local/state/baton/learning-index-reference/index.sqlite3"))
    sub=p.add_subparsers(dest="cmd",required=True)
    sub.add_parser("init")
    t=sub.add_parser("list");t.add_argument("--kind",choices=TYPES)
    t=sub.add_parser("show");t.add_argument("key")
    t=sub.add_parser("preflight");t.add_argument("key");t.add_argument("conditions")
    t=sub.add_parser("related");t.add_argument("mechanism_key")
    t=sub.add_parser("demos");t.add_argument("chat_id");t.add_argument("--task")
    t=sub.add_parser("guidance");t.add_argument("chat_id");t.add_argument("task")
    t.add_argument("--help-requested",action="store_true")
    t.add_argument("--current-blocker",action="store_true")
    args=p.parse_args(argv)
    f=Index(args.db);f.init()
    if args.cmd=="init":out={"ready":True,"always_online":False}
    elif args.cmd=="list":out=f.list(args.kind)
    elif args.cmd=="show":out=f.get(args.key)
    elif args.cmd=="preflight":out=f.preflight(args.key,args.conditions)
    elif args.cmd=="related":out=f.related(args.mechanism_key)
    elif args.cmd=="demos":out=f.demonstrations(args.chat_id,args.task)
    else:out=f.contact_guidance(args.chat_id,args.task,args.help_requested,args.current_blocker)
    print(json.dumps(out,ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
