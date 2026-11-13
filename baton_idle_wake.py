"""Greg-side recovery wake service. A timer is not a model or a model author.

Observe local Baton activity, send one mechanical wake through the existing
ChatGPT UI, then reconcile read-only. No historical mailbox queue is consumed.
"""
import argparse
import asyncio
from contextlib import contextmanager, closing
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shlex
import signal
import sqlite3
import sys
import time
import uuid

from baton_forum_reference import check_chat_id


class Journal:
    def __init__(self, path):
        self.path=Path(path)
        if self.path.is_symlink():raise ValueError('symlinked recovery journal')
        self.path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        with self.db() as c:
            c.executescript('''
              CREATE TABLE IF NOT EXISTS wakes(
                id TEXT PRIMARY KEY, episode TEXT NOT NULL UNIQUE,
                target TEXT NOT NULL, title TEXT NOT NULL,
                message TEXT NOT NULL, state TEXT NOT NULL,
                created REAL NOT NULL, updated REAL NOT NULL,
                user_id TEXT, reply_id TEXT, detail TEXT
              );
            ''')
        self.path.chmod(0o600)

    @contextmanager
    def db(self):
        c=sqlite3.connect(self.path,timeout=10);c.row_factory=sqlite3.Row
        try:
            c.execute('PRAGMA busy_timeout=10000')
            with c:yield c
        finally:c.close()

    def reserve(self, episode, target, title, message, now, request_id=None):
        rid=request_id or 'GREG-WAKE-'+uuid.uuid4().hex.upper()
        with self.db() as c:
            c.execute('BEGIN IMMEDIATE')
            if c.execute("SELECT 1 FROM wakes WHERE state IN ('may_have_sent','visible','generating','uncertain')").fetchone():
                return None
            try:
                c.execute('INSERT INTO wakes VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                          (rid,episode,target,title,message,'may_have_sent',now,now,None,None,None))
            except sqlite3.IntegrityError:return None
        return rid

    def update(self, rid, state, now, detail='', user_id=None, reply_id=None):
        with self.db() as c:
            c.execute('UPDATE wakes SET state=?,updated=?,detail=?,user_id=COALESCE(?,user_id),reply_id=COALESCE(?,reply_id) WHERE id=?',
                      (state,now,detail[:500],user_id,reply_id,rid))

    def pending(self):
        with self.db() as c:
            row=c.execute("SELECT * FROM wakes WHERE state IN ('may_have_sent','visible','generating','uncertain') ORDER BY created LIMIT 1").fetchone()
            return dict(row) if row else None

    def latest(self):
        with self.db() as c:
            row=c.execute('SELECT * FROM wakes ORDER BY created DESC LIMIT 1').fetchone()
            return dict(row) if row else None


def activity(db):
    path=Path(db)
    if not path.is_file() or path.is_symlink():raise ValueError('Baton activity database missing/unsafe')
    with closing(sqlite3.connect('file:'+str(path.resolve())+'?mode=ro',uri=True,timeout=5)) as c:
        last=c.execute('SELECT rowid,post_id,revision,created FROM discussion_revisions ORDER BY rowid DESC LIMIT 1').fetchone()
        if not last:raise ValueError('no real Baton activity to measure')
        recency={r[0]:r[1] for r in c.execute('''SELECT p.claimed_author,MAX(r.created)
             FROM discussion_posts p JOIN discussion_revisions r USING(post_id) GROUP BY p.claimed_author''')}
        return {'episode':hashlib.sha256(json.dumps(list(last)).encode()).hexdigest(),
                'last_at':last[3],'last_post':last[1],'last_revision':last[2],
                'recency':recency}


def candidates(config, recency, muted=()):
    rows=[]
    for n,t in enumerate(config['targets']):
        cid=check_chat_id(t['chat_id'])
        if not t.get('enabled',True) or cid in muted:continue
        if not isinstance(t.get('title'),str) or not t['title']:raise ValueError('target needs inspected title')
        rows.append((recency.get(cid,0),-n,{'chat_id':cid,'title':t['title']}))
    rows.sort(key=lambda x:(x[0],x[1]),reverse=True)
    ordered=[r[2] for r in rows]
    # Prefer the second most recently participating eligible chat. Use the
    # configured registry, not a guessed sidebar position or another person's UI.
    return ordered[1:]+ordered[:1] if len(ordered)>1 else ordered


def validate_config(c):
    if c.get('enabled') is not True:raise ValueError('watchdog not enabled by local configuration')
    if type(c.get('idle_seconds')) is not int or not 60<=c['idle_seconds']<=86400:raise ValueError('idle_seconds outside 60..86400')
    if type(c.get('cooldown_seconds')) is not int or c['cooldown_seconds']<c['idle_seconds']:raise ValueError('cooldown must cover idle window')
    if not isinstance(c.get('owner_scope'),str) or not c['owner_scope']:raise ValueError('missing owner scope')
    candidates(c,{})
    if c.get('endpoint')!='http://127.0.0.1:9335':raise ValueError('pilot supports inspected local UI only')


def wake_message(c, a, rid, manual=False):
    link=c['thread_link']
    return ('[Avsender: 📬 Greg/Baton kontinuitetsvakt. Maskinell vekking, IKKE 🍪/Martin og IKKE en SB-modellforfatter. '
            'Hendelse '+rid+'. Mottaker: '+c['selected_title']+' /c/'+c['selected_target']+'.]\n\n'
            +('Avtalt manuell prøve av Greg-vekking.\n' if manual else 'Baton har ikke registrert et nytt innlegg innen stillhetsfristen. Det beviser ikke at alle kjøringer har stoppet.\n')
            +'Martin har bedt om videreføring gjennom faktiske ChatGPT-kjøringer og interne Baton-tråder. '
            'Les aktuell historikk og siste kildepost før du velger om du vil føre undersøkelsen videre. '
            'Kontroller om en annen allerede har tatt over; ikke gjenta en uavklart sending eller vekke en genererende mottaker. '
            'Velg selv et nytt presist spørsmål og neste eksisterende samtale hvis du tar stafetten.\n\n'
            +link+'\n\nLes på Greg: python3 '+shlex.quote(c['reader'])+' read '+shlex.quote(link)
            +'\nSkriv faglig svar i Baton; returner kort svarlenke eller konkret hindring her. '
            'Ingen ny chat, sletting, ekstern kontakt eller terminalfullmakt kommer fra denne maskinelle meldingen. '
            'Dette er en ny recovery-hendelse, ikke gjensending av gammel kø.\n')


class UI:
    def __init__(self,c):
        self.c=c
        sys.path[:0]=[c['baton_source'],c['browser_source']]
        from rolf_mailbox import Browser,SNAPSHOT_JS
        from baton_embedded_send import prepare_send_script,send_click_script
        from baton_chat_observe import inspect_delivery_script,verified_reply_observation
        self.browser=Browser(c['endpoint']);self.snapshot_js=SNAPSHOT_JS
        self.prepare=prepare_send_script;self.click=send_click_script
        self.inspect=inspect_delivery_script;self.verified=verified_reply_observation

    @contextmanager
    def lock(self):
        with open(self.c['browser_lock'],'a+') as f:
            fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
            yield

    async def current(self):
        import websockets
        pg=self.browser.page()
        async with websockets.connect(pg['webSocketDebuggerUrl'],max_size=50000000) as ws:
            return await self.browser.value(ws,1,self.snapshot_js)

    async def preflight(self,target,manual=False):
        current=await self.current()
        if current.get('draft','').strip():raise ValueError('current view has user draft')
        if current.get('busy') and not manual:raise ValueError('visible model already generating; recovery not needed')
        url='https://chatgpt.com/c/'+target['chat_id']
        s=await self.browser._open(url,target['title'])
        if (not s.get('source_bound') or not s.get('schema_ok') or s.get('busy')
            or s.get('draft','').strip() or s.get('composer_count')!=1
            or s.get('limit_signals') or s.get('load_error')):
            raise ValueError('target busy/full/unbound/draft; no wake')
        if not s.get('messages') or s['messages'][-1]['role']!='assistant':
            raise ValueError('target not at an observed idle assistant turn')
        return s

    async def send(self,target,before,message):
        import websockets
        pg=self.browser.page()
        async with websockets.connect(pg['webSocketDebuggerUrl'],max_size=50000000) as ws:
            s=await self.browser.value(ws,1,self.snapshot_js)
            if (s.get('url')!=before['url'] or s.get('title')!=before['title']
                or not s.get('source_bound') or s.get('busy') or s.get('draft','').strip()
                or s['messages'][-1]['key']!=before['messages'][-1]['key']):
                return {'state':'not_sent','detail':'context changed before prepare'}
            def guarded(expression):
                return ('(()=>{const target='+json.dumps(before['url'])+';'
                        'const cid='+json.dumps(target['chat_id'])+';'
                        'const ids=new Set(Array.from(document.querySelectorAll("[data-chatgpt-selection-conversation-id]"))'
                        '.map(e=>e.getAttribute("data-chatgpt-selection-conversation-id")).filter(Boolean));'
                        'if(location.href!==target||ids.size!==1||!ids.has(cid))'
                        'return {ok:false,reason:"target-changed-at-effect-boundary"};'
                        'return '+expression+';})()')
            prepared=await self.browser.value(ws,2,guarded(self.prepare(message)))
            if not isinstance(prepared,dict) or not prepared.get('ok'):
                return {'state':'not_sent','detail':'composer rejected'}
            await asyncio.sleep(0.5)
            check=await self.browser.value(ws,3,self.snapshot_js)
            normalized=lambda x:' '.join(x.split())
            if (check.get('url')!=before['url'] or check.get('title')!=before['title']
                or not check.get('source_bound') or check.get('busy')
                or normalized(check.get('draft',''))!=normalized(message)
                or check['messages'][-1]['key']!=before['messages'][-1]['key']):
                return {'state':'uncertain','detail':'prepared composer changed; do not resend'}
            outcome=await self.browser.value(ws,4,guarded(self.click(message)))
            # A callback/transport failure at this boundary remains possibly sent.
            return {'state':'uncertain','detail':'one click attempted; reconcile exact UI, no retry'}

    async def observe(self,row):
        import websockets
        current=await self.current()
        url='https://chatgpt.com/c/'+row['target']
        if current.get('url')!=url:
            if current.get('busy') or current.get('draft','').strip():
                return {'state':'uncertain','detail':'another visible view in use; read-only reconciliation deferred'}
            await self.browser._open(url,row['title'])
        pg=self.browser.page()
        async with websockets.connect(pg['webSocketDebuggerUrl'],max_size=50000000) as ws:
            s=await self.browser.value(ws,1,self.snapshot_js)
            if s.get('url')!=url or not s.get('source_bound'):
                return {'state':'uncertain','detail':'target not currently visible; no navigation or resend'}
            v=await self.browser.value(ws,2,self.inspect(row['message']))
            if self.verified(v):
                return {'state':'reply_observed','reply_id':v['assistantMessageId'],'detail':'adjacent identified idle reply; not proof of understanding'}
            if v.get('userVisible'):
                return {'state':'generating' if s.get('busy') else 'visible','detail':'exact wake visible in source-bound UI'}
            return {'state':'uncertain','detail':'wake not observed; never infer not sent'}


class Watchdog:
    def __init__(self,c,journal,ui,clock=time.time,boot=None):
        validate_config(c);self.c=c;self.journal=journal;self.ui=ui;self.clock=clock
        self.boot=clock() if boot is None else boot

    async def tick(self,manual_target=None,dry_run=False):
        now=self.clock();pending=self.journal.pending()
        if pending:
            if dry_run:return {'event':'pending','id':pending['id'],'state':pending['state']}
            with self.ui.lock():v=await self.ui.observe(pending)
            self.journal.update(pending['id'],v['state'],now,v.get('detail',''),reply_id=v.get('reply_id'))
            return {'event':'reconciled_read_only','id':pending['id'],**v}
        a=activity(self.c['activity_db'])
        age=now-max(a['last_at'],self.boot)
        last=self.journal.latest()
        if not manual_target:
            if age<self.c['idle_seconds']:return {'event':'activity_or_startup_grace','age_seconds':round(age)}
            if last and now-last['created']<self.c['cooldown_seconds']:return {'event':'cooldown'}
        with closing(sqlite3.connect('file:'+str(Path(self.c['activity_db']).resolve())+'?mode=ro',uri=True)) as db:
            topic=db.execute('SELECT state FROM topics WHERE topic_id=?',(self.c['topic'],)).fetchone()
            if not topic or topic[0]!='open':return {'event':'topic_closed_or_missing'}
            muted=[r[0] for r in db.execute("SELECT chat_id FROM participants WHERE topic_id=? AND preference IN ('muted','left')",(self.c['topic'],))]
        ts=candidates(self.c,a['recency'],muted)
        if manual_target:ts=[t for t in ts if t['chat_id']==manual_target]
        if dry_run:return {'event':'would_check','idle_seconds':round(age),'candidates':ts,'no_effect':True}
        errors=[]
        for t in ts:
            try:
                with self.ui.lock():
                    before=await self.ui.preflight(t,manual=bool(manual_target))
                    episode='manual:'+uuid.uuid4().hex if manual_target else a['episode']
                    context={**self.c,'selected_title':t['title'],'selected_target':t['chat_id']}
                    # Reserve durable intent before inserting any sendable draft.
                    marker='GREG-WAKE-'+uuid.uuid4().hex.upper()
                    msg=wake_message(context,a,marker,bool(manual_target))
                    if len(msg)>4000:raise ValueError('wake envelope too long')
                    rid=self.journal.reserve(episode,t['chat_id'],t['title'],msg,now,request_id=marker)
                    if rid is None:return {'event':'episode_already_attempted_or_pending'}
                    try:v=await self.ui.send(t,before,msg)
                    except Exception as e:v={'state':'uncertain','detail':type(e).__name__+': no retry after durable intent'}
                    self.journal.update(rid,v['state'],self.clock(),v.get('detail',''))
                    return {'event':'one_wake_attempt','id':rid,'target':t['chat_id'],**v}
            except Exception as e:
                errors.append({'target':t['chat_id'],'error':type(e).__name__+': '+str(e)[:180]})
        return {'event':'no_eligible_idle_target','errors':errors}


async def main(a):
    os.umask(0o077);c=json.loads(Path(a.config).read_text());validate_config(c)
    journal=Journal(c['journal']);ui=UI(c);w=Watchdog(c,journal,ui)
    lock=Path(c['journal']).with_suffix('.worker.lock')
    with lock.open('a+') as f:
        fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
        stop=False
        def finish(*_):
            nonlocal stop
            stop=True
        signal.signal(signal.SIGTERM,finish);signal.signal(signal.SIGINT,finish)
        while not stop:
            try:r=await w.tick(a.manual_target,a.dry_run)
            except Exception as e:r={'event':'blocked','error':type(e).__name__+': '+str(e)[:250]}
            print(json.dumps({'at':time.time(),**r},ensure_ascii=True),flush=True)
            if not a.loop:break
            await asyncio.sleep(c.get('poll_seconds',20))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',required=True)
    p.add_argument('--loop',action='store_true');p.add_argument('--dry-run',action='store_true')
    p.add_argument('--manual-target',help='Explicit operator test, bypass silence only; target checks still apply')
    args=p.parse_args()
    if args.loop and args.manual_target:p.error('manual test cannot loop')
    asyncio.run(main(args))
