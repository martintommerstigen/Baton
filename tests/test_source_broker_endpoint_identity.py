"""B5/B2 R16: a pinned socket directory is not a pinned socket endpoint.

These deterministic same-UID fault injections test accidental endpoint
replacement, not a claim of resistance to hostile code sharing the service UID.
They use real Linux AF_UNIX connections and no UI, TCP, or shell execution.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import stat
import tempfile
import threading
import unittest
from unittest.mock import patch

from remote_security.source_broker import SourceBroker, Rejected, parse_request


def frame():
    return (json.dumps({"version": 1, "action": "capture",
                        "source_id": "rustworld-world", "job_id": "source0001"},
                       separators=(",", ":")) + "\n").encode()


@unittest.skipUnless(os.name == "posix" and hasattr(socket, "SO_PEERCRED"),
                     "Linux AF_UNIX peer credentials required")
class EndpointIdentityTests(unittest.TestCase):
    def setUp(self):
        if os.geteuid() == 0:
            self.skipTest("service must not run as root")
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.parent = Path(self.temp.name)
        self.parent.chmod(0o710)
        self.path = self.parent / "source.sock"
        self.allowed = os.geteuid() + 1
        self.calls = []
        self.replacement = None

        def capture(source, job):
            self.calls.append((source, job))
            return {"state": "completed_local_pinned_source",
                    "source_id": source, "job_id": job}

        self.broker = SourceBroker(str(self.path), {self.allowed},
                                   {"rustworld-world"}, capture, capture)
        self.broker.start()
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        self.broker.close()
        if self.replacement is not None:
            self.replacement.close()
            if self.path.exists() or self.path.is_symlink():
                self.path.unlink()

    def _swap_endpoint(self):
        # The parent remains the same inode; only the socket basename changes.
        self.assertTrue(stat.S_ISSOCK(self.path.lstat().st_mode))
        self.path.unlink()
        self.replacement = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.replacement.bind(str(self.path))
        self.replacement.listen(1)

    def _exchange(self):
        with patch.object(self.broker, "_peer_uid", return_value=self.allowed):
            worker = threading.Thread(target=self.broker.accept_once, daemon=True)
            worker.start()
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                client.settimeout(3)
                client.connect(str(self.path))
                client.sendall(frame())
                client.shutdown(socket.SHUT_WR)
                try:
                    reply = client.recv(4096)
                except ConnectionResetError:
                    reply = b""
            worker.join(3)
            self.assertFalse(worker.is_alive())
        return reply

    def test_replaced_endpoint_before_accept_is_rejected(self):
        self._swap_endpoint()
        with self.assertRaises(Rejected):
            self.broker.accept_once()
        self.assertEqual(self.calls, [])

    def test_replaced_endpoint_inside_accept_never_dispatches(self):
        real_accept = socket.socket.accept

        def swap_after_accept(sock):
            conn, addr = real_accept(sock)
            if sock is self.broker.sock:
                self._swap_endpoint()
            return conn, addr

        with patch.object(socket.socket, "accept", new=swap_after_accept):
            reply = self._exchange()
        self.assertEqual(reply, b"")
        self.assertEqual(self.calls, [])
        self.assertTrue(self.path.exists(), "replacement remains for inspection")

    def test_replaced_endpoint_after_parse_never_dispatches(self):
        real_parse = parse_request

        def swap_after_parse(raw, source_ids):
            request = real_parse(raw, source_ids)
            self._swap_endpoint()
            return request

        with patch("remote_security.source_broker.parse_request",
                   side_effect=swap_after_parse):
            reply = self._exchange()
        self.assertEqual(json.loads(reply)["state"],
                         "rejected_or_uncertain_no_retry")
        self.assertEqual(self.calls, [])
        self.assertTrue(self.path.exists())

    def test_replaced_endpoint_during_backend_cannot_return_success(self):
        def executed_but_endpoint_lost(source, job):
            self.calls.append((source, job))
            self._swap_endpoint()
            return {"state": "completed_local_pinned_source",
                    "source_id": source, "job_id": job}

        self.broker.capture = executed_but_endpoint_lost
        reply = self._exchange()
        self.assertEqual(self.calls, [("rustworld-world", "source0001")],
                         "backend may already have committed; never retry")
        self.assertEqual(json.loads(reply)["state"],
                         "rejected_or_uncertain_no_retry")
        self.assertTrue(self.path.exists(), "do not unlink replacement")


if __name__ == "__main__":
    unittest.main()
