"""B1/B5 experimental Unix-socket admission broker (NOT a UI sender).

An admission is NOT proof of delivery. Never retry an admitted attempt automatically.
No network listener, shell execution, browser control, or token persistence.
"""
import argparse
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import socketserver
import sqlite3
import stat
import struct
import threading
import time

MAX_REQUEST = 8192
FRAME_TIMEOUT = 3.0  # Monotonic budget for a complete request or reply.
MAX_HANDLERS = 8  # Bound concurrent connections, including partial frames.
ID = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
DIGEST = re.compile(r"^[0-9a-f]{64}$")
SCHEMA = """
CREATE TABLE IF NOT EXISTS admissions (
 conversation_id TEXT PRIMARY KEY,
 message_id TEXT NOT NULL,
 origin_turn_id TEXT NOT NULL,
 sender_id TEXT NOT NULL,
 payload_sha256 TEXT NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('admitted','uncertain')),
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


def pause_present_or_untrusted(path):
    """Fail closed for missing parents, symlinks, errors and existing marker."""
    p = Path(path).absolute()
    try:
        for parent in reversed(p.parents):
            info = parent.lstat()
            if not stat.S_ISDIR(info.st_mode):
                return True
        info = p.lstat()
        return True  # any existing marker, including symlink, means pause
    except FileNotFoundError:
        try:
            return not p.parent.is_dir()
        except OSError:
            return True
    except OSError:
        return True


class AdmissionStore:
    def __init__(self, db_path, pause_path, allowed_conversations):
        self.db_path = str(db_path)
        self.pause_path = str(pause_path)
        self.allowed = frozenset(allowed_conversations)
        with closing(self.connect()) as db:
            db.executescript(SCHEMA)

    def connect(self):
        db = sqlite3.connect(self.db_path, timeout=5, isolation_level=None)
        db.execute("PRAGMA busy_timeout=5000")
        return db

    def request(self, req):
        if not isinstance(req, dict) or type(req.get("op")) is not str:
            return {"state": "rejected", "reason": "invalid_request"}
        op = req["op"]
        if op not in ("status", "admit", "pause", "begin_click"):
            return {"state": "rejected", "reason": "unsupported_operation"}
        with closing(self.connect()) as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                paused = db.execute("SELECT value FROM settings WHERE key='paused'").fetchone()
                if op == "pause":
                    db.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('paused','1')")
                    result = {"state": "pause_recorded_not_revocation"}
                elif op == "status":
                    active = db.execute("SELECT COUNT(*) FROM admissions").fetchone()[0]
                    result = {"state": "paused" if paused or pause_present_or_untrusted(self.pause_path) else "ready",
                              "outstanding": active}
                elif paused or pause_present_or_untrusted(self.pause_path):
                    result = {"state": "rejected", "reason": "paused_or_untrusted"}
                else:
                    fields = ("conversation_id", "message_id", "origin_turn_id", "sender_id", "payload_sha256")
                    if any(type(req.get(k)) is not str for k in fields):
                        result = {"state": "rejected", "reason": "invalid_envelope"}
                    elif any(not ID.fullmatch(req[k]) for k in fields[:-1]) or not DIGEST.fullmatch(req["payload_sha256"]):
                        result = {"state": "rejected", "reason": "invalid_envelope"}
                    elif req["conversation_id"] not in self.allowed:
                        result = {"state": "rejected", "reason": "conversation_not_allowed"}
                    elif op == "begin_click":
                        # Durable, one-way pre-click transition. Commit must succeed
                        # before the caller is permitted to touch the browser.
                        # This is NOT a UI capability or a delivery receipt.
                        existing = db.execute("""SELECT message_id,origin_turn_id,sender_id,
                            payload_sha256,state FROM admissions WHERE conversation_id=?""",
                            (req["conversation_id"],)).fetchone()
                        expected = (req["message_id"], req["origin_turn_id"],
                                    req["sender_id"], req["payload_sha256"], "admitted")
                        if existing is None:
                            result = {"state": "rejected", "reason": "no_admission"}
                        elif existing != expected:
                            result = {"state": "rejected", "reason": "envelope_mismatch_or_attempt_closed"}
                        else:
                            db.execute("UPDATE admissions SET state='uncertain' WHERE conversation_id=? AND state='admitted'",
                                       (req["conversation_id"],))
                            result = {"state": "click_started_uncertain"}
                    else:
                        try:
                            db.execute("""INSERT INTO admissions
                              (conversation_id,message_id,origin_turn_id,sender_id,payload_sha256,state)
                              VALUES (?,?,?,?,?,'admitted')""", tuple(req[k] for k in fields))
                            result = {"state": "admitted_not_delivered"}
                        except sqlite3.IntegrityError:
                            # Do not disclose an old envelope or imply a duplicate was delivered.
                            result = {"state": "rejected", "reason": "outstanding_attempt"}
                db.execute("COMMIT")
                return result
            except BaseException:
                db.execute("ROLLBACK")
                raise


def read_bounded_frame(conn, limit=MAX_REQUEST):
    """Read one newline frame under a single absolute monotonic deadline.

    One-byte reads intentionally avoid accepting extra buffered frames. A peer
    that keeps trickling data cannot reset the deadline.
    """
    deadline = time.monotonic() + FRAME_TIMEOUT
    data = bytearray()
    while len(data) <= limit:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("Broker frame deadline exceeded")
        conn.settimeout(remaining)
        part = conn.recv(1)
        if not part:
            return None
        data.extend(part)
        if part == b"\n":
            return bytes(data) if len(data) <= limit else None
    return None


class BrokerHandler(socketserver.StreamRequestHandler):
    def handle(self):
        # Kernel-supplied credentials, not an asserted sender name in JSON.
        try:
            raw = self.request.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12)
            _pid, uid, _gid = struct.unpack("3i", raw)
            if uid not in self.server.allowed_uids:
                return
            data = read_bounded_frame(self.request)
            if not data:
                return
            req = json.loads(data.decode("utf-8"))
            result = self.server.store.request(req)
            self.wfile.write((json.dumps(result, sort_keys=True) + "\n").encode("utf-8"))
        except (ValueError, UnicodeError, json.JSONDecodeError, OSError, sqlite3.Error):
            # Malformed requests do not authorize a send.
            return


class Broker(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, socket_path, store, allowed_uids, max_handlers=MAX_HANDLERS):
        if type(max_handlers) is not int or max_handlers < 1:
            raise ValueError("max_handlers must be positive")
        self.store = store
        self.allowed_uids = frozenset(allowed_uids)
        self._handler_slots = threading.BoundedSemaphore(max_handlers)
        super().__init__(str(socket_path), BrokerHandler)
        os.chmod(socket_path, 0o600)

    def process_request(self, request, client_address):
        if not self._handler_slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._handler_slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._handler_slots.release()


def query(socket_path, payload):
    # The entire connect/send/response operation has one elapsed-time budget.
    deadline = time.monotonic() + FRAME_TIMEOUT
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
        conn.settimeout(FRAME_TIMEOUT)
        conn.connect(str(socket_path))
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("Broker request deadline exceeded")
        conn.settimeout(remaining)
        conn.sendall((json.dumps(payload) + "\n").encode())
        conn.shutdown(socket.SHUT_WR)
        response = bytearray()
        while not response.endswith(b"\n"):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Broker reply deadline exceeded")
            conn.settimeout(remaining)
            chunk = conn.recv(4096)
            if not chunk:
                raise RuntimeError("No authenticated broker response")
            response.extend(chunk)
            if len(response) > MAX_REQUEST:
                raise RuntimeError("Oversized response")
        return json.loads(response)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--socket", required=True)
    parser.add_argument("--db", required=True)
    parser.add_argument("--pause-path", required=True)
    parser.add_argument("--conversation", action="append", required=True)
    parser.add_argument("--allow-uid", action="append", type=int, default=[])
    args = parser.parse_args()
    # Do not remove/replace an existing socket: a second broker must fail closed.
    os.umask(0o077)
    sock = Path(args.socket)
    if sock.exists() or sock.is_symlink():
        raise SystemExit("Socket already exists; inspect existing broker before restart")
    store = AdmissionStore(args.db, args.pause_path, args.conversation)
    with Broker(sock, store, args.allow_uid or [os.getuid()]) as server:
        try:
            server.serve_forever(poll_interval=0.05)
        finally:
            sock.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
