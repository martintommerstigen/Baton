"""R22 trusted Linux kernel cross-UID contract with pinned real B1 SQLite.

Run only on trusted push under sudo, NEVER on untrusted PR code as root.
The source turn and payload are synthetic. This is NOT a ChatGPT wake.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import select
import signal
import socket
import sqlite3
import tempfile
import unittest


@unittest.skipUnless(os.name == "posix" and os.geteuid() == 0 and
                     os.environ.get("B1_H20_BROKER"),
                     "trusted root-only pinned H20 kernel test")
class CrossUIDObservedSource(unittest.TestCase):
    def test_actual_kernel_uid_handoff_spend_restart_pause(self):
        b1_path = Path(os.environ["B1_H20_BROKER"]).resolve(strict=True)
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            os.chmod(root,0o711)
            state_dir = root/"broker"
            state_dir.mkdir()
            os.chown(state_dir,21001,21001)
            os.chmod(state_dir,0o711)
            db = state_dir/"b1.sqlite"
            sock_path = state_dir/"broker.sock"
            pause = state_dir/"PAUSE_UI_WRITES"
            read_fd,write_fd = os.pipe()
            server_pid = os.fork()
            if server_pid == 0:
                os.close(read_fd)
                stage='drop_uid'
                try:
                    os.setgroups([])
                    os.setgid(21001)
                    os.setuid(21001)
                    os.umask(0o077)
                    stage='load_pinned_b1'
                    spec = importlib.util.spec_from_file_location("b1_h20_uid",b1_path)
                    b1 = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(b1)
                    from remote_security.observed_source_handoff import ObservedSourceHandoff
                    stage='create_b1_store'
                    inner = b1.AdmissionStore(db,pause,{"chat-B"})
                    proxy = ObservedSourceHandoff(inner,broker_uid=21001,
                        observer_uid=21003,controller_uid=21002,
                        source_routes={"chat-A":{"chat-B"}})
                    stage='bind_listener'
                    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as listener:
                        listener.bind(str(sock_path))
                        os.chmod(sock_path,0o777)
                        listener.listen(4)
                        listener.settimeout(12)
                        os.write(write_fd,b"ready")
                        os.close(write_fd)
                        for _ in range(10):
                            conn,_ = listener.accept()
                            with conn:
                                conn.settimeout(4)
                                data=bytearray()
                                while not data.endswith(b"\n") and len(data)<8192:
                                    part=conn.recv(1024)
                                    if not part: break
                                    data.extend(part)
                                req=json.loads(data)
                                result=proxy.request_from_socket(conn,req)
                                conn.sendall((json.dumps(result)+"\n").encode())
                    os._exit(0)
                except BaseException as exc:
                    try:
                        os.write(write_fd,("ERR:"+stage+":"+repr(exc)).encode())
                    except OSError:
                        pass
                    os._exit(2)
            os.close(write_fd)
            waited=False
            try:
                ready,_,_=select.select([read_fd],[],[],8)
                self.assertTrue(ready,"broker did not start")
                response=os.read(read_fd,1024)
                self.assertEqual(response,b"ready",response)
                os.close(read_fd)
                read_fd=-1

                def ask(uid,req):
                    rd,wr=os.pipe()
                    pid=os.fork()
                    if pid==0:
                        os.close(rd)
                        try:
                            os.setgroups([])
                            os.setgid(uid)
                            os.setuid(uid)
                            with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as client:
                                client.settimeout(5)
                                client.connect(str(sock_path))
                                client.sendall((json.dumps(req)+"\n").encode())
                                data=bytearray()
                                while not data.endswith(b"\n"):
                                    part=client.recv(4096)
                                    if not part: break
                                    data.extend(part)
                            os.write(wr,bytes(data))
                            os._exit(0)
                        except BaseException as exc:
                            os.write(wr,("ERR:"+repr(exc)).encode())
                            os._exit(2)
                    os.close(wr)
                    raw=os.read(rd,8192)
                    os.close(rd)
                    _,status=os.waitpid(pid,0)
                    self.assertTrue(os.WIFEXITED(status) and os.WEXITSTATUS(status)==0,raw)
                    return json.loads(raw)

                envelope=dict(conversation_id="chat-B",message_id="m1",
                     origin_turn_id="turn-A",sender_id="chat-A",
                     payload_sha256=hashlib.sha256(b"approved").hexdigest())
                observed=dict(envelope,op="observe_source",
                     source_text_sha256=hashlib.sha256(b"claimed source").hexdigest())
                self.assertEqual(ask(21002,observed)["reason"],"observer_only")
                self.assertEqual(ask(21003,dict(envelope,op="admit"))["reason"],"controller_only")
                self.assertEqual(ask(21003,observed)["state"],
                                 "source_observation_recorded_not_authorship")
                self.assertEqual(ask(0,dict(envelope,op="admit"))["reason"],"controller_only")
                self.assertEqual(ask(21002,dict(envelope,op="admit"))["state"],
                                 "admitted_not_delivered")
                self.assertEqual(ask(21002,dict(envelope,op="begin_click"))["state"],
                                 "click_started_uncertain")
                self.assertEqual(ask(21002,dict(envelope,op="begin_click"))["state"],
                                 "rejected")
                self.assertEqual(ask(21003,observed)["reason"],"observation_replay")
                self.assertEqual(ask(21002,dict(envelope,op="admit"))["reason"],
                                 "observation_mismatch_or_spent")
                self.assertEqual(ask(21002,{"op":"pause"})["state"],
                                 "pause_recorded_not_revocation")
                _,status=os.waitpid(server_pid,0)
                waited=True
                self.assertTrue(os.WIFEXITED(status) and os.WEXITSTATUS(status)==0)
                with sqlite3.connect(db) as conn:
                    self.assertEqual(conn.execute("SELECT state FROM admissions").fetchone()[0],
                                     "uncertain")
                    self.assertEqual(conn.execute("SELECT state FROM b5_source_witness_v1").fetchone()[0],
                                     "spent")
                    self.assertEqual(conn.execute("SELECT value FROM settings WHERE key='paused'").fetchone()[0],
                                     "1")
            finally:
                if read_fd!=-1:
                    os.close(read_fd)
                if not waited:
                    try: os.kill(server_pid,signal.SIGTERM)
                    except ProcessLookupError: pass
                    os.waitpid(server_pid,0)


if __name__ == "__main__":
    unittest.main()
