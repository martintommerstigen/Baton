"""Offline protocol tests for authenticated loopback Baton adapter."""
import tempfile
import unittest
from baton_loopback_http import dispatch

class LoopbackTests(unittest.TestCase):
    def test_unauthorized(self):
        with tempfile.TemporaryDirectory() as workspace:
            status, _ = dispatch("/v1/execute", {"operation": "identity"}, "bad", "good-token", workspace)
            self.assertEqual(status, 401)
    def test_missing_server_secret_denies(self):
        with tempfile.TemporaryDirectory() as workspace:
            status, _ = dispatch("/v1/execute", {"operation": "identity"}, "", "", workspace)
            self.assertEqual(status, 401)
    def test_unknown_operation_denied(self):
        with tempfile.TemporaryDirectory() as workspace:
            status, _ = dispatch("/v1/execute", {"operation": "bash"}, "good-token", "good-token", workspace)
            self.assertEqual(status, 400)
    def test_extra_arguments_denied(self):
        with tempfile.TemporaryDirectory() as workspace:
            status, _ = dispatch("/v1/execute", {"operation": "identity", "args": ["-a"]}, "good-token", "good-token", workspace)
            self.assertEqual(status, 400)
    def test_authorized_identity(self):
        with tempfile.TemporaryDirectory() as workspace:
            status, result = dispatch("/v1/execute", {"operation": "identity"}, "good-token", "good-token", workspace)
            self.assertEqual(status, 200)
            self.assertTrue(result["ok"])
    def test_wrong_path(self):
        with tempfile.TemporaryDirectory() as workspace:
            status, _ = dispatch("/health", {"operation": "identity"}, "good-token", "good-token", workspace)
            self.assertEqual(status, 404)

if __name__ == "__main__":
    unittest.main()
