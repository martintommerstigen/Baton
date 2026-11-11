"""Real AF_UNIX + SQLite contract for B5 credential gate; synthetic messages.

This is a minimal B1-compatible store, not an assertion that B1 H21 itself
has been deployed or that an existing ChatGPT conversation was observed.
"""
import hashlib
import json
import os
from pathlib import Path
import socket
import socketserver
import sqlite3
import tempfile
import threading
import unittest

from remote_security.frame_credentials import (
    CredentialBoundBrokerHandler, UntrustedFrame, install_credential_bound_handler)


class DurableScopedStore:
    def __init__(self, path, pause):
        self.path = path
        self.pause = pause
        with sqlite3.connect(path) as db:
            db.execute('CREATE TABLE IF NOT EXISTS attempts (message_id TEXT PRIMARY KEY, state TEXT)')

    def request_from_socket(self, conn, req):
        if req.get('op') not in ('admit', 'begin_click'):
            return {'state':'rejected'}
        if self.pause.exists():
            return {'state':'rejected','reason':'paused_or_untrusted'}
        if set(req) != {'op','message_id','payload_sha256'} or req['message_id']!='m1':
            return {'state':'rejected','reason':'bad_envelope'}
        if req['payload_sha256'] != hashlib.sha256(b'approved').hexdigest():
            return {'state':'rejected','reason':'wrong_payload'}
        with sqlite3.connect(self.path, timeout=3) as db:
            if req['op']=='admit':
                try:
                    db.execute('INSERT INTO attempts VALUES (?,?)',('m1','admitted'))
                    return {'state':'admitted_not_delivered'}
                except sqlite3.IntegrityError:
                    return {'state':'rejected','reason':'replay'}
            changed=db.execute('UPDATE attempts SET state=? WHERE message_id=? AND state=?',
                               ('uncertain','m1','admitted')).rowcount
            return {'state':'click_started_uncertain' if changed else 'rejected'}


class B1CompatibleBroker(socketserver.ThreadingMixIn,socketserver.UnixStreamServer):
    daemon_threads=True
    def __init__(self,path,store,uid):
        self.store=store
        self.allowed_uids=frozenset({uid})
        super().__init__(path,CredentialBoundBrokerHandler)
    def endpoint_unchanged(self):
        return os.path.exists(self.server_address)


@unittest.skipUnless(os.name=='posix' and os.geteuid()!=0, 'non-root contract')
class Contract(unittest.TestCase):
    def test_socket_sqlite_pause_restart_replay(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            store=DurableScopedStore(str(root/'attempt.sqlite'),root/'PAUSE_UI_WRITES')
            path=str(root/'broker.sock')
            broker=B1CompatibleBroker(path,store,os.getuid())
            install_credential_bound_handler(broker)
            t=threading.Thread(target=broker.serve_forever,kwargs={'poll_interval':.01})
            t.start()
            req={'op':'admit','message_id':'m1','payload_sha256':hashlib.sha256(b'approved').hexdigest()}
            def ask(r):
                with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as s:
                    s.settimeout(2);s.connect(path)
                    s.sendall((json.dumps(r)+'\n').encode())
                    return json.loads(s.recv(4096))
            try:
                self.assertEqual(ask(req)['state'],'admitted_not_delivered')
                self.assertEqual(ask(req)['reason'],'replay')
                store.pause.touch()
                self.assertEqual(ask(dict(req,op='begin_click'))['reason'],'paused_or_untrusted')
                store.pause.unlink()
                self.assertEqual(ask(dict(req,op='begin_click'))['state'],'click_started_uncertain')
            finally:
                broker.shutdown();broker.server_close();t.join(timeout=3)
                os.unlink(path)  # disposable test endpoint; B1 owns production unlink
            broker=B1CompatibleBroker(path,store,os.getuid())
            install_credential_bound_handler(broker)
            t=threading.Thread(target=broker.serve_forever,kwargs={'poll_interval':.01});t.start()
            try:
                self.assertEqual(ask(req)['reason'],'replay')
                self.assertEqual(ask(dict(req,op='begin_click'))['state'],'rejected')
            finally:
                broker.shutdown();broker.server_close();t.join(timeout=3)


class InstallNegatives(unittest.TestCase):
    def test_legacy_broker_denied(self):
        with self.assertRaises(UntrustedFrame):install_credential_bound_handler(object())


if __name__=='__main__':unittest.main()
