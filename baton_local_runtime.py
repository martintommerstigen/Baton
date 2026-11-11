"""Baton-owned local Core lifetime. No remote listener, root, or GitHub relay.

The core runs on 127.0.0.1 only and is stopped when this Baton UI exits.
A previously started same-token local Core can be reused after verification.
"""
import errno
import os
from pathlib import Path
from threading import Thread
from http.server import ThreadingHTTPServer

from baton_local_api import handler_factory, load_token


def start_local_core(*, port=52526, token_file=None):
    if os.geteuid() == 0:
        raise PermissionError("Baton Core refuses root")
    path = Path(token_file) if token_file else Path.home()/".config/baton/local-api-token"
    token = load_token(path)
    try:
        server = ThreadingHTTPServer(("127.0.0.1", port), handler_factory(token))
    except OSError as exc:
        if exc.errno != errno.EADDRINUSE or port != 52526 or token_file is not None:
            raise
        # A previously started Baton Core is acceptable ONLY if it is reachable
        # with this user's private token and executes a harmless test correctly.
        from baton_core_client import execute_on_greg
        try:
            result = execute_on_greg(["/usr/bin/true"], str(Path.home()), 5)
        except (ValueError, OSError, RuntimeError) as verify_error:
            raise RuntimeError("port 52526 occupied by unverified local service") from verify_error
        if result.get("exit_code") != 0:
            raise RuntimeError("existing Baton Core failed authenticated probe")
        return None
    Thread(target=server.serve_forever, name="baton-local-core", daemon=True).start()
    return server


def stop_local_core(server):
    if server is not None:
        server.shutdown()
        server.server_close()
