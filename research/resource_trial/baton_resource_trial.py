"""Isolated resource contract; NOT connected to Greg's active wake service.

Observations, authorization, recipient outcomes and physical effect ownership
are separate inputs. Policy/router callbacks represent trusted adapters in this
trial; they do not authenticate a model or create production owner grants.
"""
from contextlib import contextmanager
from dataclasses import dataclass
import json
from pathlib import Path
import sqlite3
import uuid


@dataclass(frozen=True)
class Action:
    id: str
    recipient: str
    route: str
    operation: str = 'send'
    intent: str = ''


@dataclass(frozen=True)
class Observation:
    recipient: str
    route: str
    resources: tuple
    ready: bool
    seen_at: float
    expires: float


class Broker:
    def __init__(self,path,router,policy):
        self.path=Path(path);self.router=router;self.policy=policy
        with self.db() as c:
            c.executescript('''
              CREATE TABLE IF NOT EXISTS actions(
                id TEXT PRIMARY KEY, recipient TEXT NOT NULL,
                route TEXT NOT NULL, operation TEXT NOT NULL,
                state TEXT NOT NULL, resources TEXT NOT NULL,
                token TEXT NOT NULL, expires REAL NOT NULL, intent TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS resources(
                resource TEXT PRIMARY KEY, generation INTEGER NOT NULL,
                owner TEXT, phase TEXT NOT NULL);
            ''')

    @contextmanager
    def db(self):
        c=sqlite3.connect(self.path,timeout=10);c.row_factory=sqlite3.Row
        try:
            with c:yield c
        finally:c.close()

    def _resources(self,a):
        keys=tuple(sorted(set(self.router(a))))
        if not keys or any(not isinstance(x,str) or not x or len(x)>180 for x in keys):
            raise ValueError('adapter must declare actual effect resources')
        return keys

    def _observed(self,a,o,keys,now):
        return (o.recipient==a.recipient and o.route==a.route and
                tuple(sorted(set(o.resources)))==keys and o.ready is True
                and o.seen_at<=now<o.expires)

    def acquire(self,a,o,now,ttl=5):
        if ttl<=0 or ttl>30:raise ValueError('bounded effect turn required')
        keys=self._resources(a)
        # A fresh observation is NOT authorization; a free resource isn't either.
        if self.policy(a,now) is not True:return {'state':'denied_by_policy'}
        if not self._observed(a,o,keys,now):return {'state':'needs_observation'}
        with self.db() as c:
            c.execute('BEGIN IMMEDIATE')
            if c.execute('SELECT 1 FROM actions WHERE id=?',(a.id,)).fetchone():
                return {'state':'existing_intent_no_replay'}
            for old in c.execute("SELECT id FROM actions WHERE state='leased' AND expires<=?",(now,)).fetchall():
                c.execute("UPDATE actions SET state='expired_before_effect' WHERE id=?",(old['id'],))
                c.execute("UPDATE resources SET owner=NULL,phase='free' WHERE owner=?",(old['id'],))
            # As Siv already corrected: a recipient is not an intention boundary.
            # The adapter supplies stable intent keys; this model cannot infer
            # whether a caller is lying about two actions being independent.
            intent=a.intent or a.id
            pending=c.execute("SELECT id FROM actions WHERE intent=? AND state IN ('leased','inflight','waiting','delivery_uncertain','effect_uncertain')",(intent,)).fetchone()
            if pending:return {'state':'intent_pending','id':pending['id']}
            occupied=[]
            for key in keys:
                row=c.execute('SELECT * FROM resources WHERE resource=?',(key,)).fetchone()
                if row and row['owner']:
                    owner=c.execute('SELECT state,expires FROM actions WHERE id=?',(row['owner'],)).fetchone()
                    # Only a never-dispatched lease may expire and be fenced out.
                    # Inflight or physically uncertain work is NOT freed by time.
                    if owner and owner['state']=='leased' and owner['expires']<=now:
                        c.execute("UPDATE actions SET state='expired_before_effect' WHERE id=?",(row['owner'],))
                        c.execute("UPDATE resources SET owner=NULL,phase='free' WHERE owner=?",(row['owner'],))
                    else:occupied.append(key)
            if occupied:return {'state':'deferred_by_effect_resource','resources':occupied}
            token=uuid.uuid4().hex;generations={}
            for key in keys:
                c.execute("INSERT OR IGNORE INTO resources VALUES(?,0,NULL,'free')",(key,))
                c.execute("UPDATE resources SET generation=generation+1,owner=?,phase='leased' WHERE resource=?",(a.id,key))
                generations[key]=c.execute('SELECT generation FROM resources WHERE resource=?',(key,)).fetchone()[0]
            c.execute('INSERT INTO actions VALUES(?,?,?,?,?,?,?,?,?)',
                      (a.id,a.recipient,a.route,a.operation,'leased',json.dumps(keys),token,now+ttl,intent))
            return {'state':'leased','id':a.id,'token':token,'generations':generations}

    def begin_effect(self,a,o,lease,now):
        """Last model gate; a real adapter must enforce its fence at dispatch too."""
        keys=self._resources(a)
        if self.policy(a,now) is not True:return False
        if not self._observed(a,o,keys,now):return False
        with self.db() as c:
            c.execute('BEGIN IMMEDIATE')
            row=c.execute('SELECT * FROM actions WHERE id=?',(a.id,)).fetchone()
            if not row or row['state']!='leased' or row['token']!=lease.get('token') or row['expires']<=now:return False
            if (row['recipient'],row['route'],row['operation'],tuple(json.loads(row['resources'])))!=(a.recipient,a.route,a.operation,keys):return False
            if row['intent']!=(a.intent or a.id):return False
            for key in keys:
                r=c.execute('SELECT owner,generation FROM resources WHERE resource=?',(key,)).fetchone()
                if not r or r['owner']!=a.id or r['generation']!=lease.get('generations',{}).get(key):return False
            c.execute("UPDATE actions SET state='inflight' WHERE id=?",(a.id,))
            c.execute("UPDATE resources SET phase='inflight' WHERE owner=?",(a.id,))
            return True

    def effect_result(self,action_id,token,*,physical_finished,delivery):
        if delivery not in ('visible','unknown','not_sent'):raise ValueError('invalid result')
        with self.db() as c:
            c.execute('BEGIN IMMEDIATE')
            row=c.execute('SELECT state,token FROM actions WHERE id=?',(action_id,)).fetchone()
            if not row or row['state']!='inflight' or row['token']!=token:return False
            if physical_finished:
                state={'visible':'waiting','unknown':'delivery_uncertain','not_sent':'not_sent'}[delivery]
                c.execute("UPDATE resources SET owner=NULL,phase='free' WHERE owner=?",(action_id,))
            else:
                state='effect_uncertain'
                c.execute("UPDATE resources SET phase='uncertain' WHERE owner=?",(action_id,))
            c.execute('UPDATE actions SET state=? WHERE id=?',(state,action_id))
            return True

    def outcome(self,action_id):
        with self.db() as c:
            row=c.execute('SELECT * FROM actions WHERE id=?',(action_id,)).fetchone()
            return dict(row) if row else None
