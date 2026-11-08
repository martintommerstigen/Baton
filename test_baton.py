import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from server import app, database

class BatonTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.db=os.path.join(self.tmp.name,'db.sqlite3')
        database(self.db).close()
        self.http=ThreadingHTTPServer(('127.0.0.1',0),app(self.db,{'a':'a'*40,'b':'b'*40}))
        self.thread=threading.Thread(target=self.http.serve_forever,daemon=True); self.thread.start()
        self.url='http://127.0.0.1:'+str(self.http.server_port)
    def tearDown(self):
        self.http.shutdown(); self.http.server_close(); self.thread.join(); self.tmp.cleanup()
    def call(self, who, path, data=None):
        req=urllib.request.Request(self.url+path, data=json.dumps(data).encode() if data is not None else None, headers={'Authorization':'Bearer '+who*40,'Content-Type':'application/json'})
        try:
            with urllib.request.urlopen(req) as r:return r.status,json.load(r)
        except urllib.error.HTTPError as e:return e.code,json.load(e)
    def test_roundtrip_and_authorization(self):
        status,send=self.call('a','/v1/send',{'id':'one','to':'b','body':'Hello'})
        self.assertEqual((status,send['status']),(202,'queued'))
        self.assertEqual(self.call('a','/v1/inbox')[1]['messages'],[])
        self.assertEqual(self.call('a','/v1/ack',{'id':'one'})[0],404)
        self.assertEqual(self.call('b','/v1/inbox')[1]['messages'][0]['body'],'Hello')
        self.assertEqual(self.call('b','/v1/ack',{'id':'one'})[0],200)
        self.assertEqual(self.call('b','/v1/inbox')[1]['messages'],[])
    def test_idempotency_and_conflict(self):
        m={'id':'x','to':'b','body':'Hi'}
        self.assertEqual(self.call('a','/v1/send',m)[0],202)
        self.assertEqual(self.call('a','/v1/send',m)[0],202)
        self.assertEqual(self.call('a','/v1/send',{**m,'body':'changed'})[0],409)
        self.assertEqual(len(self.call('b','/v1/inbox')[1]['messages']),1)
    def test_concurrent_conflicting_send(self):
        import concurrent.futures
        import threading
        barrier=threading.Barrier(2)
        def send(body):
            barrier.wait()
            return self.call('a','/v1/send',{'id':'raced','to':'b','body':body})
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            a=pool.submit(send,'First')
            b=pool.submit(send,'Second')
            results=[a.result(),b.result()]
        self.assertEqual(sorted(code for code,_ in results),[202,409])
        winning_body=self.call('b','/v1/inbox')[1]['messages'][0]['body']
        accepted_body='First' if results[0][0]==202 else 'Second'
        self.assertEqual(winning_body,accepted_body)
        self.assertEqual(self.call('a','/v1/send',{'id':'raced','to':'b','body':winning_body})[0],202)
        self.assertEqual(self.call('a','/v1/send',{'id':'raced','to':'b','body':'different'})[0],409)

    def test_retry_after_ack_reports_lifecycle(self):
        msg={'id':'lifecycle','to':'b','body':'Once'}
        self.assertEqual(self.call('a','/v1/send',msg)[1]['status'],'queued')
        self.assertEqual(self.call('a','/v1/send',msg)[1]['status'],'already_queued')
        self.assertEqual(self.call('b','/v1/ack',{'id':'lifecycle'})[1]['status'],'client_acknowledged')
        self.assertEqual(self.call('a','/v1/send',msg)[1]['status'],'client_acknowledged')
        self.assertEqual(self.call('b','/v1/inbox')[1]['messages'],[])
        self.assertEqual(self.call('a','/v1/send',{**msg,'body':'Changed'})[0],409)

    def test_invalid_destination(self):
        self.assertEqual(self.call('a','/v1/send',{'to':'unknown','body':'Hi'})[0],400)
        self.assertEqual(self.call('a','/v1/send',{'to':'a','body':'Hi'})[0],400)
if __name__=='__main__':unittest.main()