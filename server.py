#!/usr/bin/env python3
"""GTRCM Baton v0: authenticated, append-only, pull-based relay. Python stdlib only.
Bind to loopback by default. Put behind HTTPS reverse proxy for remote clients.
"""
import argparse
from contextlib import closing
import hmac
import json
import os
import sqlite3
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

MAX_BODY = 16384

def database(path):
    db = sqlite3.connect(path, timeout=10)
    db.execute('PRAGMA journal_mode=WAL')
    db.execute('CREATE TABLE IF NOT EXISTS messages (id TEXT PRIMARY KEY, sender TEXT NOT NULL, recipient TEXT NOT NULL, body TEXT NOT NULL, created INTEGER NOT NULL, read_at INTEGER)')
    db.commit()
    return db

def app(db_path, tokens):
    class Handler(BaseHTTPRequestHandler):
        def reply(self, code, data):
            blob = json.dumps(data, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(blob)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(blob)
        def identity(self):
            provided = self.headers.get('Authorization', '')
            for name, token in tokens.items():
                if hmac.compare_digest(provided, 'Bearer ' + token):
                    return name
            return None
        def do_GET(self):
            who = self.identity()
            parsed = urlparse(self.path)
            if parsed.path in ('/mobile', '/mobile/'):
                page = os.path.join(os.path.dirname(__file__), 'mobile', 'index.html')
                with open(page, 'rb') as f:
                    content = f.read()
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Security-Policy', "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
                self.send_header('X-Content-Type-Options', 'nosniff')
                self.send_header('Cache-Control', 'no-store')
                self.send_header('Content-Length', str(len(content)))
                self.end_headers()
                self.wfile.write(content)
                return
            if not who: return self.reply(401, {'error':'unauthorized'})
            if parsed.path != '/v1/inbox': return self.reply(404, {'error':'not_found'})
            with closing(database(db_path)) as db, db:
                rows = db.execute('SELECT id,sender,body,created FROM messages WHERE recipient=? AND read_at IS NULL ORDER BY created,id LIMIT 100', (who,)).fetchall()
            self.reply(200, {'recipient':who,'messages':[dict(zip(('id','sender','body','created'), r)) for r in rows]})
        def do_POST(self):
            who = self.identity()
            if not who: return self.reply(401, {'error':'unauthorized'})
            if self.path not in ('/v1/send','/v1/ack'): return self.reply(404, {'error':'not_found'})
            try:
                size = int(self.headers.get('Content-Length','0'))
                if not 0 < size <= MAX_BODY: return self.reply(413, {'error':'invalid_size'})
                data = json.loads(self.rfile.read(size))
                if not isinstance(data, dict): raise ValueError()
            except (ValueError, json.JSONDecodeError): return self.reply(400, {'error':'invalid_json'})
            if self.path == '/v1/send':
                to, body = data.get('to'), data.get('body')
                mid = data.get('id') or str(uuid.uuid4())
                if to not in tokens or to == who or not isinstance(body,str) or not body.strip() or len(body)>8000 or not isinstance(mid,str) or len(mid)>128:
                    return self.reply(400, {'error':'invalid_message'})
                # Atomic first-writer-wins: an ignored conflicting insert must not
                # receive a false 202 receipt. Compare the durable winning row.
                with closing(database(db_path)) as db, db:
                    inserted = db.execute('INSERT OR IGNORE INTO messages VALUES (?,?,?,?,?,NULL)',
                                          (mid,who,to,body,int(time.time()))).rowcount
                    stored = db.execute('SELECT sender,recipient,body,read_at FROM messages WHERE id=?',
                                        (mid,)).fetchone()
                    conflict = stored is None or stored[:3] != (who,to,body)
                    state = ('queued' if inserted else
                             'client_acknowledged' if stored[3] is not None else 'already_queued') if not conflict else None
                if conflict:
                    return self.reply(409, {'error':'id_conflict'})
                return self.reply(202, {'id':mid,'status':state})
            mid = data.get('id')
            if not isinstance(mid,str): return self.reply(400, {'error':'invalid_id'})
            with closing(database(db_path)) as db, db:
                cur = db.execute('UPDATE messages SET read_at=COALESCE(read_at,?) WHERE id=? AND recipient=?',(int(time.time()),mid,who))
                found = cur.rowcount == 1
            if not found:
                return self.reply(404, {'error':'not_in_your_inbox'})
            return self.reply(200, {'id':mid,'status':'client_acknowledged'})
        def log_message(self, fmt, *args):
            pass
    return Handler

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--host',default='127.0.0.1')
    p.add_argument('--port',type=int,default=8765)
    p.add_argument('--db',default=os.path.join(os.path.dirname(__file__),'baton.sqlite3'))
    p.add_argument('--tokens',default=os.path.join(os.path.dirname(__file__),'tokens.json'))
    args=p.parse_args()
    with open(args.tokens) as f: tokens=json.load(f)
    if not isinstance(tokens,dict) or len(tokens)<2 or any(not isinstance(v,str) or len(v)<32 for v in tokens.values()) or len(set(tokens.values()))!=len(tokens):
        raise SystemExit('Need 2+ distinct strong tokens')
    if args.host not in ('127.0.0.1','::1','localhost'):
        raise SystemExit('Refusing public HTTP bind; use HTTPS reverse proxy with access controls')
    database(args.db).close()
    server=ThreadingHTTPServer((args.host,args.port),app(args.db,tokens))
    print(f'GTRCM Baton listening on {args.host}:{args.port}',flush=True)
    server.serve_forever()
if __name__=='__main__': main()