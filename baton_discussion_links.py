"""Direct local Baton discussion posts, pinned read links, no chat sending.

Reuses Forum topics. Local OS access permits writing; claimed ChatGPT identities
are NOT authenticated. Links are references, never credentials or effect grants.
"""
import argparse
from contextlib import contextmanager
import getpass
import json
import os
from pathlib import Path
import re
import sqlite3
import time
from urllib.parse import parse_qsl, urlencode, urlsplit
import uuid

from baton_forum_reference import Forum, check_chat_id, check_topic_id

KINDS = ('question', 'reply', 'correction', 'counterexample', 'note', 'decision')
RUN = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9_.:-]{2,120}$')
HINTS = ('kind', 'from', 'to', 'topic', 'until', 'sort')


def post_id(value):
    if not isinstance(value, str) or str(uuid.UUID(value)) != value:
        raise ValueError('noncanonical post ID')
    return value


class Discussion:
    def __init__(self, db, receipts=None, clock=time.time):
        self.path = Path(db)
        self.clock = clock
        self.forum = Forum(self.path, receipts or self.path.parent/'receipts')

    @contextmanager
    def db(self):
        if self.path.is_symlink():
            raise ValueError('symlinked discussion database')
        c = sqlite3.connect(str(self.path), timeout=10)
        c.row_factory = sqlite3.Row
        try:
            c.execute('PRAGMA foreign_keys=ON')
            with c:
                yield c
        finally:
            c.close()

    def init(self):
        if self.path.is_symlink():
            raise ValueError('symlinked discussion database')
        self.forum.init()
        with self.db() as c:
            c.executescript('''
              CREATE TABLE IF NOT EXISTS discussion_posts(
                post_id TEXT PRIMARY KEY,
                topic_id TEXT NOT NULL REFERENCES topics(topic_id),
                claimed_author TEXT NOT NULL,
                reply_post TEXT REFERENCES discussion_posts(post_id),
                reply_revision INTEGER,
                CHECK((reply_post IS NULL)=(reply_revision IS NULL))
              );
              CREATE TABLE IF NOT EXISTS discussion_revisions(
                post_id TEXT NOT NULL REFERENCES discussion_posts(post_id),
                revision INTEGER NOT NULL CHECK(revision>0),
                author_run TEXT NOT NULL,
                recipient TEXT NOT NULL,
                kind TEXT NOT NULL,
                body TEXT NOT NULL,
                created INTEGER NOT NULL,
                invitation_until INTEGER,
                source_evidence TEXT,
                transport_actor TEXT NOT NULL,
                verification_state TEXT NOT NULL CHECK(verification_state='claimed_local_writer'),
                PRIMARY KEY(post_id,revision)
              );
            ''')

    def thread(self, topic, title):
        self.forum.create_topic(topic, title)

    def write(self, topic, author, run, body, *, recipient='all', kind='note',
              ttl=None, source_evidence=None, reply=None, revise=None,
              expected_revision=None):
        topic = check_topic_id(topic)
        author = check_chat_id(author)
        if recipient != 'all':
            recipient = check_chat_id(recipient)
        if not isinstance(run, str) or not RUN.fullmatch(run):
            raise ValueError('invalid run ID')
        if kind not in KINDS or not isinstance(body, str) or not 1 <= len(body.strip()) <= 30000:
            raise ValueError('invalid post kind/body')
        if ttl is not None and (type(ttl) is not int or not 1 <= ttl <= 2592000):
            raise ValueError('invitation TTL must be 1..2592000 seconds')
        if source_evidence is not None and (not isinstance(source_evidence, str) or len(source_evidence)>500):
            raise ValueError('invalid citation')
        if revise and reply:
            raise ValueError('revision cannot change reply target')
        parent = self.read(reply)['post'] if reply else None
        if parent and parent['topic_id'] != topic:
            raise ValueError('reply belongs to another topic; cite instead')
        now = int(self.clock())
        with self.db() as c:
            c.execute('BEGIN IMMEDIATE')
            t = c.execute('SELECT state FROM topics WHERE topic_id=?',(topic,)).fetchone()
            if not t or t['state']!='open':
                raise ValueError('topic absent or closed')
            pid = post_id(revise) if revise else str(uuid.uuid4())
            revision = 1
            if revise:
                old=c.execute('SELECT * FROM discussion_posts WHERE post_id=?',(pid,)).fetchone()
                if not old or old['topic_id']!=topic or old['claimed_author']!=author:
                    raise ValueError('revision must retain topic and claimed author')
                latest=c.execute('SELECT MAX(revision) FROM discussion_revisions WHERE post_id=?',(pid,)).fetchone()[0]
                if type(expected_revision) is not int or latest!=expected_revision:
                    raise ValueError('revision conflict; reread before revising')
                revision=latest+1
            else:
                c.execute('INSERT INTO discussion_posts VALUES(?,?,?,?,?)',
                          (pid,topic,author,parent['post_id'] if parent else None,
                           parent['revision'] if parent else None))
            c.execute('INSERT INTO discussion_revisions VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                      (pid,revision,run,recipient,kind,body.strip(),now,
                       now+ttl if ttl else None,source_evidence,
                       'local-os:'+str(os.getuid()),'claimed_local_writer'))
        return self.link(topic,pid,revision)

    def _get(self, topic, pid, revision):
        with self.db() as c:
            row=c.execute('''SELECT p.*,r.* FROM discussion_posts p
                JOIN discussion_revisions r USING(post_id)
                WHERE p.topic_id=? AND p.post_id=? AND r.revision=?''',
                (topic,pid,revision)).fetchone()
            if not row:
                raise ValueError('post/revision not found in this topic')
            result=dict(row)
            latest=c.execute('SELECT MAX(revision) FROM discussion_revisions WHERE post_id=?',(pid,)).fetchone()[0]
        return result,latest

    @staticmethod
    def _hints(row, sort='oldest'):
        return {'kind':row['kind'],'from':row['claimed_author'],'to':row['recipient'],
                'topic':row['topic_id'],'until':str(row['invitation_until'] or ''),'sort':sort}

    def link(self, topic, pid, revision):
        row,_=self._get(check_topic_id(topic),post_id(pid),revision)
        return 'baton://local/t/'+topic+'/p/'+pid+'?'+urlencode({'v':str(revision),**self._hints(row)})

    def read(self, link):
        if not isinstance(link,str) or len(link)>2048:
            raise ValueError('invalid link')
        u=urlsplit(link)
        if u.scheme!='baton' or u.netloc!='local' or u.fragment:
            raise ValueError('expected local read-only Baton link')
        parts=u.path.split('/')
        if len(parts)!=5 or parts[1]!='t' or parts[3]!='p':
            raise ValueError('invalid post route')
        topic=check_topic_id(parts[2]);pid=post_id(parts[4])
        pairs=parse_qsl(u.query,keep_blank_values=True,strict_parsing=True)
        q=dict(pairs)
        if len(q)!=len(pairs) or set(q)!={'v',*HINTS} or not re.fullmatch(r'[1-9][0-9]{0,8}',q['v']):
            raise ValueError('invalid or repeated link metadata')
        if q['sort'] not in ('oldest','newest'):
            raise ValueError('invalid sort hint')
        row,latest=self._get(topic,pid,int(q['v']))
        canonical=self._hints(row,q['sort'])
        mismatches=[k for k in HINTS if canonical[k]!=q[k]]
        return {'post':row,'metadata_mismatches':mismatches,
                'invitation_expired':row['invitation_until'] is not None and self.clock()>=row['invitation_until'],
                'latest_revision':latest,'newer_revision_available':latest!=row['revision'],
                'latest_link':self.link(topic,pid,latest),
                'authority':'none: reading never sends, grants access, or acknowledges understanding'}

    def posts(self, topic):
        topic=check_topic_id(topic)
        with self.db() as c:
            rows=c.execute('''SELECT p.post_id,MAX(r.revision) AS rev FROM discussion_posts p
                JOIN discussion_revisions r USING(post_id) WHERE p.topic_id=?
                GROUP BY p.post_id ORDER BY MIN(r.created),p.post_id''',(topic,)).fetchall()
        return [self.read(self.link(topic,r['post_id'],r['rev'])) for r in rows]


def main():
    os.umask(0o077)
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--db',default=str(Path.home()/'.local/state/baton/council/topics.sqlite3'))
    sub=p.add_subparsers(dest='command',required=True)
    t=sub.add_parser('thread');t.add_argument('topic');t.add_argument('title')
    t=sub.add_parser('read');t.add_argument('link')
    t=sub.add_parser('list');t.add_argument('topic')
    for name in ('post','reply','revise'):
        t=sub.add_parser(name);t.add_argument('target')
        t.add_argument('--chat',required=True);t.add_argument('--run',required=True)
        t.add_argument('--body-file',type=Path,required=True)
        t.add_argument('--to',default='all');t.add_argument('--kind',choices=KINDS,default='reply' if name=='reply' else 'note')
        t.add_argument('--ttl',type=int);t.add_argument('--source')
    a=p.parse_args();d=Discussion(a.db);d.init()
    if a.command=='thread':d.thread(a.topic,a.title);result={'topic':a.topic}
    elif a.command=='read':result=d.read(a.link)
    elif a.command=='list':result=d.posts(a.topic)
    else:
        kw={}
        if a.command in ('reply','revise'):
            target=d.read(a.target)['post'];topic=target['topic_id']
            kw={'reply':a.target} if a.command=='reply' else {'revise':target['post_id'],'expected_revision':target['revision']}
        else:topic=a.target
        result={'link':d.write(topic,a.chat,a.run,a.body_file.read_text(encoding='utf8'),recipient=a.to,kind=a.kind,ttl=a.ttl,source_evidence=a.source,**kw)}
    print(json.dumps(result,ensure_ascii=True,indent=2))


if __name__=='__main__':main()
