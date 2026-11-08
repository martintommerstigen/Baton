import pathlib,sys,tempfile,threading,unittest,urllib.request
from http.server import ThreadingHTTPServer
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from server import app,database

class MobileTest(unittest.TestCase):
    def test_mobile_page_and_security_headers(self):
        with tempfile.TemporaryDirectory() as folder:
            db=str(pathlib.Path(folder)/'db.sqlite')
            database(db).close()
            server=ThreadingHTTPServer(('127.0.0.1',0),app(db,{'a':'a'*40,'b':'b'*40}))
            thread=threading.Thread(target=server.serve_forever,daemon=True)
            thread.start()
            try:
                with urllib.request.urlopen(f'http://127.0.0.1:{server.server_port}/mobile') as r:
                    html=r.read().decode()
                    self.assertIn('Baton Mobile',html)
                    self.assertIn('/v1/send',html)
                    self.assertIn('/v1/inbox',html)
                    self.assertIn('/v1/ack',html)
                    self.assertIn('Content-Security-Policy',r.headers)
                    self.assertNotIn('localStorage',html)
            finally:
                server.shutdown();server.server_close();thread.join()
if __name__=='__main__':unittest.main()