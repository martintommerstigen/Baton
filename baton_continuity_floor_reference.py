"""Experimental local Baton coordination: overlapping runs and scoped writer turns.

No network server, no ChatGPT API/DOM interaction, no external writes.
A row marked "running" is NOT proof that an LLM is actively generating.
The local caller must independently authenticate the running agent, and
the UI/effect adapters MUST enforce the resulting fencing token. This
reference module does neither, and cannot guarantee uninterrupted activity.
"""
from contextlib import contextmanager
import hashlib
from pathlib import Path
import re
import sqlite3
from baton_private_sqlite_reference import check_private_sqlite_path, prepare_private_sqlite

RUN_ID = re.compile(r"^[0-9a-f]{32}$", re.I)
CHAT_ID = re.compile(r"^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$", re.I)
RESOURCE = re.compile(r"^[a-z0-9][a-z0-9.:_-]{2,127}$")
OFFER = re.compile(r"^[a-z0-9][a-z0-9_-]{2,127}$")


def _id(pattern, value):
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise ValueError("invalid identifier")
    return value.lower()


def _seconds(now):
    if not isinstance(now, int) or isinstance(now, bool) or now < 0:
        raise ValueError("invalid integer time")
    return now


class Floor:
    def __init__(self, database, heartbeat_ttl=30):
        self.path = Path(database)
        if not isinstance(heartbeat_ttl, int) or heartbeat_ttl < 1:
            raise ValueError("invalid heartbeat TTL")
        self.ttl = heartbeat_ttl

    @contextmanager
    def _db(self):
        prepare_private_sqlite(self.path)
        con = sqlite3.connect(str(self.path), timeout=10)
        try:
            con.execute("PRAGMA busy_timeout=10000")
            con.execute("PRAGMA foreign_keys=ON")
            with con:
                yield con
        finally:
            con.close()

    def init(self):
        # Refuse nested aliases before mkdir() can follow them and create
        # directories outside the intended local state tree.
        check_private_sqlite_path(self.path)
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with self._db() as c:
            c.executescript("""
                CREATE TABLE IF NOT EXISTS runs(
                  run_id TEXT PRIMARY KEY, chat_id TEXT NOT NULL,
                  joined_at INTEGER NOT NULL, last_seen INTEGER NOT NULL,
                  state TEXT NOT NULL CHECK(state IN ('running','released'))
                );
                CREATE TABLE IF NOT EXISTS transfers(
                  offer_id TEXT PRIMARY KEY,
                  from_run TEXT NOT NULL REFERENCES runs(run_id),
                  to_run TEXT NOT NULL REFERENCES runs(run_id),
                  state TEXT NOT NULL CHECK(state IN ('offered','accepted','consumed')),
                  created_at INTEGER NOT NULL,
                  CHECK(from_run != to_run)
                );
                CREATE TABLE IF NOT EXISTS writer_turns(
                  resource TEXT PRIMARY KEY,
                  owner_run TEXT NOT NULL REFERENCES runs(run_id),
                  token_sha256 TEXT NOT NULL,
                  generation INTEGER NOT NULL,
                  expires_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS events(
                  event_id INTEGER PRIMARY KEY,
                  time_sec INTEGER NOT NULL, kind TEXT NOT NULL,
                  run_id TEXT, subject TEXT NOT NULL
                );
            """)

    def _event(self, c, now, kind, run, subject):
        c.execute("INSERT INTO events(time_sec,kind,run_id,subject) VALUES(?,?,?,?)",
                  (now,kind,run,subject))

    def _live(self,c,run,now):
        row=c.execute("SELECT last_seen,state FROM runs WHERE run_id=?",(run,)).fetchone()
        return bool(row and row[1]=="running" and row[0]<=now and row[0]+self.ttl>=now)

    def join(self,run_id,chat_id,now):
        run=_id(RUN_ID,run_id); chat=_id(CHAT_ID,chat_id); _seconds(now)
        with self._db() as c:
            c.execute("BEGIN IMMEDIATE")
            # An old run ID is never revived. Fresh run ID required after a stop.
            c.execute("INSERT INTO runs VALUES(?,?,?,?,'running')",(run,chat,now,now))
            self._event(c,now,"joined",run,chat)

    def heartbeat(self,run_id,now):
        run=_id(RUN_ID,run_id);_seconds(now)
        with self._db() as c:
            c.execute("BEGIN IMMEDIATE")
            row=c.execute("SELECT last_seen,state FROM runs WHERE run_id=?",(run,)).fetchone()
            if not row or row[1]!="running" or now<row[0]:
                return False
            if now>row[0]+self.ttl:
                # A stale runner cannot create a fictional unbroken liveness trace.
                self._event(c,now,"late-heartbeat-rejected",run,run)
                return False
            c.execute("UPDATE runs SET last_seen=? WHERE run_id=?",(now,run))
            return True

    def offer(self,offer_id,source,target,now):
        oid=_id(OFFER,offer_id); a=_id(RUN_ID,source); b=_id(RUN_ID,target);_seconds(now)
        if a==b: raise ValueError("self transfer invalid")
        with self._db() as c:
            c.execute("BEGIN IMMEDIATE")
            if not self._live(c,a,now) or not self._live(c,b,now):
                return False
            c.execute("INSERT INTO transfers VALUES(?,?,?,'offered',?)",(oid,a,b,now))
            self._event(c,now,"offered",a,oid)
            return True

    def accept(self,offer_id,recipient,now):
        oid=_id(OFFER,offer_id); b=_id(RUN_ID,recipient);_seconds(now)
        with self._db() as c:
            c.execute("BEGIN IMMEDIATE")
            row=c.execute("SELECT from_run,to_run,state FROM transfers WHERE offer_id=?",
                          (oid,)).fetchone()
            if not row or row[1]!=b or row[2]!="offered":
                return False
            if not self._live(c,row[0],now) or not self._live(c,b,now):
                return False
            c.execute("UPDATE transfers SET state='accepted' WHERE offer_id=?",(oid,))
            self._event(c,now,"accepted",b,oid)
            return True

    def release(self,run_id,offer_id,now):
        a=_id(RUN_ID,run_id); oid=_id(OFFER,offer_id);_seconds(now)
        with self._db() as c:
            c.execute("BEGIN IMMEDIATE")
            row=c.execute("SELECT from_run,to_run,state FROM transfers WHERE offer_id=?",
                          (oid,)).fetchone()
            if not row or row[0]!=a or row[2]!="accepted":
                return False
            if not self._live(c,a,now) or not self._live(c,row[1],now):
                return False
            if c.execute("SELECT 1 FROM writer_turns WHERE owner_run=? AND expires_at>? LIMIT 1",
                         (a,now)).fetchone():
                # Cannot abandon an outstanding writer turn.
                return False
            c.execute("UPDATE runs SET state='released' WHERE run_id=?",(a,))
            c.execute("UPDATE transfers SET state='consumed' WHERE offer_id=?",(oid,))
            self._event(c,now,"released",a,oid)
            return True

    def acquire_writer(self,resource,run_id,token,now,ttl=15):
        resource=_id(RESOURCE,resource);run=_id(RUN_ID,run_id)
        token=_id(RUN_ID,token);_seconds(now)
        if not isinstance(ttl,int) or isinstance(ttl,bool) or not 1<=ttl<=120:
            raise ValueError("invalid writer TTL")
        digest=hashlib.sha256(token.encode()).hexdigest()
        with self._db() as c:
            c.execute("BEGIN IMMEDIATE")
            if not self._live(c,run,now):
                return None
            row=c.execute("SELECT owner_run,generation,expires_at FROM writer_turns WHERE resource=?",
                          (resource,)).fetchone()
            if row and row[2]>now:
                return None  # Same owner must release or wait, not overwrite token.
            gen=(row[1]+1 if row else 1)
            c.execute("""INSERT INTO writer_turns(resource,owner_run,token_sha256,generation,expires_at)
                         VALUES(?,?,?,?,?)
                         ON CONFLICT(resource) DO UPDATE SET owner_run=excluded.owner_run,
                         token_sha256=excluded.token_sha256,generation=excluded.generation,
                         expires_at=excluded.expires_at""",
                      (resource,run,digest,gen,now+ttl))
            self._event(c,now,"writer-acquired",run,resource)
            return gen

    def writer_valid(self,resource,run_id,token,generation,now):
        resource=_id(RESOURCE,resource);run=_id(RUN_ID,run_id)
        token=_id(RUN_ID,token);_seconds(now)
        if not isinstance(generation,int) or generation<1:
            raise ValueError("invalid generation")
        digest=hashlib.sha256(token.encode()).hexdigest()
        with self._db() as c:
            if not self._live(c,run,now):
                return False
            row=c.execute("""SELECT 1 FROM writer_turns
                WHERE resource=? AND owner_run=? AND token_sha256=?
                AND generation=? AND expires_at>?""",
                (resource,run,digest,generation,now)).fetchone()
            return bool(row)

    def writer_release(self,resource,run_id,token,generation,now):
        resource=_id(RESOURCE,resource);run=_id(RUN_ID,run_id)
        token=_id(RUN_ID,token);_seconds(now)
        if not isinstance(generation,int) or generation<1:
            raise ValueError("invalid generation")
        with self._db() as c:
            c.execute("BEGIN IMMEDIATE")
            n=c.execute("""UPDATE writer_turns SET expires_at=?
                WHERE resource=? AND owner_run=? AND token_sha256=?
                AND generation=? AND expires_at>?""",
                (now,resource,run,hashlib.sha256(token.encode()).hexdigest(),generation,now)).rowcount
            if n:self._event(c,now,"writer-released",run,resource)
            return n==1

    def status(self,now):
        _seconds(now)
        with self._db() as c:
            rows=c.execute("SELECT run_id,chat_id,last_seen,state FROM runs ORDER BY joined_at,run_id").fetchall()
            active=[{"run_id":r[0],"chat_id":r[1],"last_seen":r[2]} for r in rows
                    if r[3]=="running" and r[2]<=now<=r[2]+self.ttl]
            return {"active_attested_runners":active,
                    "floor_observed":bool(active),
                    "guaranteed_model_generation":False,
                    "expired_or_released":len(rows)-len(active)}

    def history(self):
        with self._db() as c:
            return c.execute("SELECT time_sec,kind,run_id,subject FROM events ORDER BY event_id").fetchall()
