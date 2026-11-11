"""Optional pinned *actual* B1 H21 Broker/SQLite with B5 frame guard.

No source-turn authorship or R22 role authorization is implied. The wrapper
below is deliberately cooperative-only; R22 still must be installed for
production role policy. The separate kernel tests cover credential forgery.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import socket
import tempfile
import threading
import unittest

from remote_security.frame_credentials import install_credential_bound_handler


class ScopedCooperativeTestAdapter:
    def __init__(self, inner):self.inner=inner
    def request_from_socket(self, accepted_socket, req):
        return self.inner.request(req)


@unittest.skipUnless(os.environ.get('B1_H21_BROKER') and os.geteuid()!=0,
                     'requires pinned B1 source and non-root Linux runner')
class ActualB1Contract(unittest.TestCase):
    def test_actual_b1_sqlite_pause_restart_and_no_retry(self):
        spec=importlib.util.spec_from_file_location('pinned_b1_h21_broker',
             Path(os.environ['B1_H21_BROKER']).resolve(strict=True))
        b1=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(b1)
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            os.chmod(root,0o700)
            sock=root/'actual-b1.sock'
            db=root/'b1.sqlite'
            pause=root/'PAUSE_UI_WRITES'
            envelope=dict(conversation_id='chat-B',message_id='m1',
                          origin_turn_id='turn-A',sender_id='chat-A',
                          payload_sha256=hashlib.sha256(b'approved').hexdigest())
            def ask(req):
                with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as client:
                    client.settimeout(3)
                    client.connect(str(sock))
                    client.sendall((json.dumps(req,sort_keys=True)+'\n').encode())
                    response=bytearray()
                    while not response.endswith(b'\n'):
                        part=client.recv(4096)
                        if not part:break
                        response.extend(part)
                    return json.loads(response) if response else None
            for generation in range(2):
                inner=b1.AdmissionStore(db,pause,{'chat-B'})
                broker=b1.Broker(sock,ScopedCooperativeTestAdapter(inner),[os.getuid()])
                install_credential_bound_handler(broker)
                thread=threading.Thread(target=broker.serve_forever,
                          kwargs={'poll_interval':0.01},daemon=True)
                thread.start()
                try:
                    if generation==0:
                        self.assertEqual(ask(dict(envelope,op='admit'))['state'],
                                         'admitted_not_delivered')
                        self.assertEqual(ask(dict(envelope,op='admit'))['state'],'rejected')
                        pause.touch()
                        self.assertEqual(ask(dict(envelope,op='begin_click'))['reason'],
                                         'paused_or_untrusted')
                        pause.unlink()
                        self.assertEqual(ask(dict(envelope,op='begin_click'))['state'],
                                         'click_started_uncertain')
                    else:
                        self.assertEqual(ask(dict(envelope,op='admit'))['state'],'rejected')
                        self.assertEqual(ask(dict(envelope,op='begin_click'))['state'],'rejected')
                finally:
                    broker.shutdown();broker.server_close();thread.join(timeout=5)
                    self.assertFalse(thread.is_alive())


if __name__=='__main__':unittest.main()
