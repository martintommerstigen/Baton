"""Fail-closed read-only local gateway for Baton, without shell or browser access.

This is a transport bootstrap, NOT a ChatGPT wake controller. Bind loopback only;
use SSH port forwarding or a private authenticated tunnel for remote clients.
"""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hmac
import json
import os
from pathlib import Path
import stat

DEFAULT_PAUSE = Path.home() / 'GTRCM-newborn-bootstrap/transport/PAUSE_UI_WRITES'


def load_token_file(path):
    """Read a local owner-only token file, rejecting links and loose permissions."""
    flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_CLOEXEC', 0)
    fd = os.open(path, flags)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise PermissionError('token file must be regular, owner-owned, mode 0600 or 0400')
        raw = os.read(fd, 257)
        if len(raw) > 256:
            raise ValueError('token file too long')
        token = raw.rstrip(b'\r\n')
        if len(token) < 32 or len(token) > 256 or any(c < 33 or c > 126 for c in token):
            raise ValueError('token must contain 32-256 printable ASCII bytes without spaces')
        return token.decode('ascii')
    finally:
        os.close(fd)


def pause_active(path):
    """A symlink (including dangling) or unreadable path is a pause, not clearance."""
    try:
        os.lstat(path)
        return True
    except FileNotFoundError:
        return False
    except OSError:
        return True


class Gateway(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, port, token, pause_file=DEFAULT_PAUSE):
        if not isinstance(token, str) or len(token) < 32:
            raise ValueError('token required')
        self.token = token
        self.pause_file = Path(pause_file)
        super().__init__(('127.0.0.1', port), Handler)


class Handler(BaseHTTPRequestHandler):
    server_version = 'BatonRemote/0.1'
    sys_version = ''

    def log_message(self, format, *args):
        # No headers, credentials, query strings or payloads in logs.
        pass

    def _reply(self, status, body):
        encoded = json.dumps(body, sort_keys=True, separators=(',', ':')).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Length', str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _authorized(self):
        host = self.headers.get('Host', '')
        if host.split(':')[0].lower() not in ('127.0.0.1', 'localhost') or '@' in host:
            self._reply(403, {'error': 'host_rejected'})
            return False
        supplied = self.headers.get('Authorization', '')
        if not hmac.compare_digest(supplied, 'Bearer ' + self.server.token):
            self._reply(401, {'error': 'unauthorized'})
            return False
        return True

    def do_GET(self):
        if not self._authorized():
            return
        if self.path == '/v1/health':
            self._reply(200, {'service': 'baton-remote', 'version': 1, 'mode': 'read-only', 'status': 'ok'})
        elif self.path == '/v1/pause-status':
            self._reply(200, {'ui_writes_paused': pause_active(self.server.pause_file)})
        else:
            self._reply(404, {'error': 'operation_not_allowlisted'})

    def do_POST(self):
        if self._authorized():
            self._reply(405, {'error': 'read_only_no_write_operations'})

    def do_PUT(self):
        self.do_POST()

    def do_DELETE(self):
        self.do_POST()


def main(argv=None):
    parser = argparse.ArgumentParser(description='Loopback-only read-only Baton gateway')
    parser.add_argument('--port', type=int, default=8787)
    parser.add_argument('--pause-file', type=Path, default=DEFAULT_PAUSE)
    parser.add_argument('--token-file', required=True, help='owner-only token file, not a CLI token')
    args = parser.parse_args(argv)
    token = load_token_file(args.token_file)
    with Gateway(args.port, token, args.pause_file) as server:
        print('Baton Remote read-only gateway listening on 127.0.0.1:%d' % server.server_port, flush=True)
        server.serve_forever()


if __name__ == '__main__':
    main()
