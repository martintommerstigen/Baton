import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from baton_core_client import execute_on_greg, CORE_URL

class FakeResponse:
    status=200
    def __enter__(self):
        return self
    def __exit__(self,*a):
        return None
    def read(self,n):
        return json.dumps({"exit_code":0,"output":"Greg\n","truncated":False}).encode()

class CoreClientTests(unittest.TestCase):
    def test_exact_loopback_and_private_token(self):
        with TemporaryDirectory() as tmp:
            token_file=Path(tmp)/"token"
            token_file.write_text("a"*64+"\n")
            token_file.chmod(0o600)
            with patch("baton_core_client.urllib.request.urlopen",return_value=FakeResponse()) as mock:
                result=execute_on_greg(["/usr/bin/hostname"],"/home/olliver",15,token_file=token_file)
            req=mock.call_args.args[0]
            self.assertEqual(req.full_url,CORE_URL)
            self.assertIn("127.0.0.1",req.full_url)
            self.assertEqual(req.get_header("Authorization"),"Bearer "+"a"*64)
            self.assertEqual(json.loads(req.data)["argv"],["/usr/bin/hostname"])
            self.assertEqual(result["exit_code"],0)
    def test_unsafe_token_file_denied(self):
        with TemporaryDirectory() as tmp:
            path=Path(tmp)/"token"
            path.write_text("a"*64)
            path.chmod(0o644)
            with self.assertRaises(ValueError):
                execute_on_greg(["echo","test"],"/tmp",15,token_file=path)

if __name__=="__main__":
    unittest.main()
