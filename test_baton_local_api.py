import http.client
import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from baton_local_api import handler_factory, load_token

class LocalAPITests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.token="a"*64
        self.server=ThreadingHTTPServer(("127.0.0.1",0),handler_factory(self.token))
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
    def request(self,token,payload):
        conn=http.client.HTTPConnection("127.0.0.1",self.server.server_port,timeout=5)
        conn.request("POST","/v1/exec",json.dumps(payload),
                     {"Authorization":"Bearer "+token,"Content-Type":"application/json"})
        res=conn.getresponse()
        body=json.loads(res.read())
        conn.close()
        return res.status,body
    def test_unauthorized(self):
        code,_=self.request("wrong",{"argv":["true"],"cwd":str(self.root),"timeout":3})
        self.assertEqual(code,401)
    def test_local_exec(self):
        with patch("baton_exec_agent.os.geteuid",return_value=1000):
            code,result=self.request(self.token,{"argv":["python3","-c","print('local')"],
                                                  "cwd":str(self.root),"timeout":3})
        self.assertEqual(code,200)
        self.assertEqual(result["output"].strip(),"local")
    def test_invalid_shape(self):
        code,_=self.request(self.token,{"argv":["true"]})
        self.assertEqual(code,400)
    def test_token_permissions(self):
        path=self.root/"token"
        self.assertEqual(len(load_token(path)),64)
        self.assertEqual(path.stat().st_mode & 0o777,0o600)
        path.chmod(0o644)
        with self.assertRaises(ValueError):
            load_token(path)
if __name__=="__main__":
    unittest.main()
