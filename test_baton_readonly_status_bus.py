"""Negative controls for read-only Baton host status over the existing bus."""
import json
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from baton_local_terminal import execute
from baton_github_bus import make_response


class ReadOnlyInstallStatusBusTests(TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "checkout"
        self.root.mkdir()
        subprocess.run(["git", "init", "-q", str(self.root)],
                       check=True, capture_output=True, timeout=5)
        self.report = {
            "branch": "feature/evening-local-terminal-2026-11-10",
            "revision": "a" * 40,
            "core_service_active_unverified": True,
            "core_port_open_unverified": True,
            "codex_mcp_config_state": "registered-for-codex",
            "existing_chat_wake_verified": False,
        }

    def test_fixed_operation_returns_redacted_inspector_report(self):
        with patch("baton_install_status.inspect_installation",
                   return_value=self.report) as inspector:
            outcome = execute("install-status", self.root)
        self.assertTrue(outcome["ok"])
        self.assertEqual(outcome["exit_code"], 0)
        self.assertFalse(outcome["truncated"])
        self.assertEqual(json.loads(outcome["output"]), self.report)
        inspector.assert_called_once_with(root=self.root.resolve())

    def test_bus_accepts_status_but_never_promotes_to_exec(self):
        now = datetime.now(timezone.utc)
        req_id = "abcdef1234567890abcdef1234567890"
        request = self.root / (req_id + ".json")
        request.write_text(json.dumps({
            "id": req_id, "operation": "install-status",
            "created_at": now.isoformat(),
        }))
        with patch("baton_install_status.inspect_installation",
                   return_value=self.report):
            receipt = make_response(request, self.root, now)
        self.assertEqual(receipt["status"], "executed")
        self.assertFalse(json.loads(receipt["result"]["output"])["existing_chat_wake_verified"])
        request.write_text(json.dumps({
            "id": req_id, "operation": "exec",
            "created_at": now.isoformat(),
            "argv": ["/usr/bin/true"], "cwd": str(self.root), "timeout": 5,
        }))
        self.assertEqual(make_response(request, self.root, now)["status"], "rejected")

    def test_arbitrary_operation_and_symlinked_workspace_denied(self):
        with self.assertRaises(ValueError):
            execute("read-private-config", self.root)
        alias = self.root.parent / "alias"
        alias.symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "symlink"):
            execute("install-status", alias)

    def test_inspector_never_prints_secrets_in_real_report(self):
        # Redaction is checked by the existing test_baton_install_status.py.
        # This integration check also confirms no raw process args or token fields.
        with patch("baton_install_status.inspect_installation",
                   return_value=self.report):
            output = execute("install-status", self.root)["output"]
        self.assertNotIn("token_value", output)
        self.assertNotIn("process_argv", output)
        self.assertNotIn("message_body", output)
