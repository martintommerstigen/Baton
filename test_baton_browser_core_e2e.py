"""An actual local write and independent readback through the Baton Core path.

This exercises NativeHostSession -> local authenticated HTTP Core -> subprocess
as the test user's own account. It never touches Greg or public networking.
"""
from http.server import ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from unittest.mock import patch
import sys
import unittest

from baton_browser_native_host import NativeHostSession
from baton_core_client import execute_on_greg
from baton_local_api import handler_factory, load_token
from baton_model_protocol import render_tool_call_v2

CHAT = "6aef828e-0150-83eb-bbac-061f79a8fd4a"


class BridgeCoreLiveLocalTests(unittest.TestCase):
    def test_authenticated_write_then_independent_read(self):
        with TemporaryDirectory() as folder:
            root=Path(folder)
            token_file=root/"private"/"core-token"
            token=load_token(token_file)
            server=ThreadingHTTPServer(("127.0.0.1",0),handler_factory(token))
            thread=Thread(target=server.serve_forever,daemon=True)
            thread.start()
            try:
                url=f"http://127.0.0.1:{server.server_port}/v1/exec"
                def core(argv,cwd,timeout):
                    return execute_on_greg(argv,cwd,timeout,token_file=token_file)
                session=NativeHostSession(client=core,lease=lambda:True)
                arm=session.handle({"op":"arm","chat_id":CHAT})
                nonce=arm["nonce"]
                self.assertEqual(arm["chat_id"],CHAT)

                def call(request_id,argv):
                    frame=render_tool_call_v2(nonce,{
                        "request_id":request_id,"tool":"greg_exec",
                        "argv":argv,"cwd":str(root),"timeout":5
                    })
                    reply=session.handle({
                        "op":"execute_frame","chat_id":CHAT,"frame":frame
                    })
                    self.assertTrue(reply["ok"],reply)
                    return reply

                with patch("baton_core_client.CORE_URL",url):
                    write=call("b"*32,[sys.executable,"-c",
                        "from pathlib import Path; Path('proof.txt').write_text('baton-write-ok')"])
                    self.assertIn('"exit_code":0',write["frame"])
                    read=call("c"*32,[sys.executable,"-c",
                        "from pathlib import Path; print(Path('proof.txt').read_text())"])
                    self.assertIn("baton-write-ok",read["frame"])
                    self.assertEqual((root/"proof.txt").read_text(),"baton-write-ok")
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)


if __name__=="__main__":
    unittest.main()
