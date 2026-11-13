"""Isolated tests of read-only raw CDP discovery exposure."""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
import unittest
from contextlib import contextmanager

from baton_cdp_boundary_audit import audit_port


@contextmanager
def fixture(version, pages):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path not in ("/json/version", "/json/list"):
                self.send_error(404)
                return
            payload = version if self.path == "/json/version" else pages
            body = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    th = Thread(target=server.serve_forever, daemon=True)
    th.start()
    try:
        yield server.server_address[1]
    finally:
        server.shutdown()
        th.join(timeout=3)
        server.server_close()


class BoundaryAuditTests(unittest.TestCase):
    def test_uncredentialed_page_websocket_discovery_is_bypass_opportunity(self):
        with fixture({}, [{"type": "page", "url": "https://private.example",
                           "webSocketDebuggerUrl": "ws://127.0.0.1:1234/devtools/page/secret"}]) as p:
            result = audit_port(p)
        self.assertTrue(result["raw_discovery_exposed"])
        self.assertEqual("raw_cdp_bypass_opportunity", result["status"])
        self.assertNotIn("private.example", json.dumps(result))
        self.assertNotIn("secret", json.dumps(result))

    def test_browser_websocket_alone_counts(self):
        with fixture({"webSocketDebuggerUrl": "ws://127.0.0.1:1234/devtools/browser/key"}, []) as p:
            result = audit_port(p)
        self.assertTrue(result["browser_websocket_disclosed"])
        self.assertTrue(result["raw_discovery_exposed"])
        self.assertEqual(0, result["page_count"])

    def test_no_raw_websocket_has_no_positive_bypass_proof(self):
        with fixture({"Browser": "test"}, [{"type": "page"}]) as p:
            result = audit_port(p)
        self.assertFalse(result["raw_discovery_exposed"])
        self.assertEqual("endpoint_reachable_no_websocket_disclosed", result["status"])

    def test_wrong_json_is_undetermined_not_secure(self):
        with fixture({"Browser": "test"}, {"wrong": "shape"}) as p:
            result = audit_port(p)
        self.assertEqual("discovery_failed_ValueError", result["status"])
        self.assertFalse(result["raw_discovery_exposed"])

    def test_port_validation_blocks_non_loopback_use_and_bad_range(self):
        with self.assertRaises(ValueError):
            audit_port(-5)
        with self.assertRaises(ValueError):
            audit_port(65536)
        with self.assertRaises(ValueError):
            audit_port("9335")


if __name__ == "__main__":
    unittest.main()
