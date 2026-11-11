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


def checked_socket_parent(socket_path):
    """Validate the public AF_UNIX parent before obtaining a directory capability.

    The service-owned final directory must not be group/world writable.
    Root-owned sticky ancestors such as /tmp are permitted. This is not a
    defense against a malicious process with the same effective UID.
    """
    raw = os.fspath(socket_path)
    if (type(raw) is not str or not raw.startswith("/")
            or raw != str(Path(raw)) or Path(raw).name in ("", ".", "..")):
        raise ValueError("noncanonical broker socket path")
    path = Path(raw)
    current = Path("/")
    for component in path.parent.parts[1:]:
        current = current / component
        info = current.lstat()
        if not stat.S_ISDIR(info.st_mode):
            raise ValueError("symlink or non-directory broker ancestor")
        if info.st_mode & 0o022 and not (info.st_uid == 0 and info.st_mode & stat.S_ISVTX):
            raise ValueError("writable broker ancestor")
    parent = path.parent.lstat()
    if parent.st_uid != os.geteuid() or parent.st_mode & 0o022:
        raise ValueError("broker socket parent must be service-owned and not writable by others")
    return path, (parent.st_dev, parent.st_ino)


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
            # A renamed/replaced public parent must not authorize a new
            # admission through a previously accepted connection.
            if not self.server.parent_unchanged():
                return
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
        self.public_path, self.parent_identity = checked_socket_parent(socket_path)
        self.parent_fd = None
        self.bound_inode = None
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
        directory_fd = os.open(self.public_path.parent, flags)
        try:
            parent = os.fstat(directory_fd)
            if ((parent.st_dev, parent.st_ino) != self.parent_identity
                    or not self._same_public_parent(directory_fd)):
                raise ValueError("broker parent changed before bind")
            try:
                os.stat(self.public_path.name, dir_fd=directory_fd, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                raise FileExistsError("broker endpoint already exists; never replace it")
            self.parent_fd = directory_fd
            # AF_UNIX bind resolves the basename through the pinned directory
            # descriptor, not through a mutable public pathname.
            pinned_path = f"/proc/self/fd/{directory_fd}/{self.public_path.name}"
            super().__init__(pinned_path, BrokerHandler)
            st = os.stat(self.public_path.name, dir_fd=directory_fd, follow_symlinks=False)
            if not stat.S_ISSOCK(st.st_mode) or st.st_uid != os.geteuid():
                raise ValueError("broker bound an untrusted endpoint")
            self.bound_inode = (st.st_dev, st.st_ino)
            os.chmod(self.public_path.name, 0o600, dir_fd=directory_fd,
                     follow_symlinks=False)
            st = os.stat(self.public_path.name, dir_fd=directory_fd, follow_symlinks=False)
            if ((st.st_dev, st.st_ino) != self.bound_inode
                    or not stat.S_ISSOCK(st.st_mode) or st.st_mode & 0o077
                    or not self.parent_unchanged()):
                raise ValueError("broker endpoint changed during bind")
        except BaseException:
            if hasattr(self, "socket"):
                self.socket.close()
            if self.parent_fd is not None:
                self._unlink_own_socket()
                self.parent_fd = None
            os.close(directory_fd)
            raise

    def _same_public_parent(self, directory_fd):
        try:
            _, identity = checked_socket_parent(str(self.public_path))
            pinned = os.fstat(directory_fd)
            return identity == (pinned.st_dev, pinned.st_ino) == self.parent_identity
        except (OSError, ValueError):
            return False

    def parent_unchanged(self):
        return self.parent_fd is not None and self._same_public_parent(self.parent_fd)

    def _unlink_own_socket(self):
        """Remove only the socket inode created by this instance, via dirfd."""
        if self.parent_fd is None or self.bound_inode is None:
            return
        try:
            st = os.stat(self.public_path.name, dir_fd=self.parent_fd,
                         follow_symlinks=False)
            if stat.S_ISSOCK(st.st_mode) and (st.st_dev, st.st_ino) == self.bound_inode:
                os.unlink(self.public_path.name, dir_fd=self.parent_fd)
        except FileNotFoundError:
            pass

    def process_request(self, request, client_address):
        if not self.parent_unchanged():
            self.shutdown_request(request)
            return
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

    def server_close(self):
        try:
            super().server_close()
        finally:
            if self.parent_fd is not None:
                try:
                    self._unlink_own_socket()
                finally:
                    os.close(self.parent_fd)
                    self.parent_fd = None
                    self.bound_inode = None


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
            # Broker.server_close removes only its own pinned socket inode.
            # Never unlink an attacker-replaced public path on shutdown.
            pass


if __name__ == "__main__":
    main()
