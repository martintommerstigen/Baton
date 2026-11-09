"""Durable wake ledger. A queued message is not proof of a chat waking."""
import sqlite3
import time

class WakeLedger:
    def __init__(self, path):
        self.path = str(path)
        with self.db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS wakes (
                id TEXT PRIMARY KEY, source TEXT NOT NULL, target TEXT NOT NULL,
                digest TEXT NOT NULL, state TEXT NOT NULL, observed_turn TEXT,
                updated INTEGER NOT NULL)""")
    def db(self):
        return sqlite3.connect(self.path, timeout=10)
    def request(self, id, source, target, digest):
        if not all(isinstance(x,str) and x.strip() for x in (id,source,target,digest)) or source==target:
            raise ValueError("invalid wake request")
        with self.db() as db:
            db.execute("INSERT OR IGNORE INTO wakes VALUES (?,?,?,?,?,?,?)",
                       (id,source,target,digest,"requested",None,int(time.time())))
            row=db.execute("SELECT source,target,digest,state FROM wakes WHERE id=?",(id,)).fetchone()
            if row[:3] != (source,target,digest):
                raise ValueError("conflicting request ID")
            return row[3]
    def state(self,id):
        with self.db() as db:
            row=db.execute("SELECT target,state,observed_turn FROM wakes WHERE id=?",(id,)).fetchone()
            return row
    def begin_submission(self,id):
        # Persist intent BEFORE interacting with UI. Do not retry after uncertainty.
        with self.db() as db:
            return bool(db.execute("UPDATE wakes SET state='submitting',updated=? WHERE id=? AND state='requested'",
                                   (int(time.time()),id)).rowcount)
    def mark_uncertain(self,id):
        with self.db() as db:
            return bool(db.execute("UPDATE wakes SET state='uncertain',updated=? WHERE id=? AND state='submitting'",
                                   (int(time.time()),id)).rowcount)
    def verify(self,id,observed_chat,observed_turn):
        if not observed_chat or not observed_turn:
            raise ValueError("observed chat and turn required")
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row=db.execute("SELECT target,state,observed_turn FROM wakes WHERE id=?",(id,)).fetchone()
            if row is None or row[0]!=observed_chat:
                raise ValueError("wrong target chat")
            if row[1]=="verified":
                if row[2]!=observed_turn:
                    raise ValueError("conflicting observed turn")
                return False
            if row[1] not in ("submitting","uncertain"):
                raise ValueError("no submission initiated")
            db.execute("UPDATE wakes SET state='verified',observed_turn=?,updated=? WHERE id=?",
                       (observed_turn,int(time.time()),id))
            return True
