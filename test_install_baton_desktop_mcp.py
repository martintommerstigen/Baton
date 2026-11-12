import json
import os
from pathlib import Path
import stat
import sys
from tempfile import TemporaryDirectory
import tomllib
import unittest
from unittest.mock import patch

from install_baton_desktop_mcp import install
from baton_mcp_stdio import handle
from baton_local_runtime import start_local_core, stop_local_core
import baton_core_client


class DesktopMcpInstallTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.script = self.root / "baton_mcp_stdio.py"
        self.script.write_text("# safe test file", encoding="utf-8")
        self.config = self.root / "codex" / "config.toml"

    def test_preserves_unrelated_config_and_idempotent(self):
        self.config.parent.mkdir()
        self.config.write_text("model = \"gpt-6\"\n[features]\nalpha = true\n", encoding="utf-8")
        self.assertEqual(install(self.config, self.script, sys.executable), "installed")
        installed = self.config.read_text()
        self.assertIn('model = "gpt-6"', installed)
        self.assertEqual(install(self.config, self.script, sys.executable), "already-configured")
        self.assertEqual(self.config.read_text(), installed)
        data = tomllib.loads(installed)
        server = data["mcp_servers"]["baton_greg"]
        self.assertEqual(server["args"], [str(self.script.resolve())])
        self.assertEqual(server["command"], sys.executable)
        self.assertEqual(server["default_tools_approval_mode"], "prompt")
        self.assertEqual(stat.S_IMODE(self.config.stat().st_mode), 0o600)

    def test_existing_auto_approval_is_not_silently_rewritten(self):
        self.config.parent.mkdir()
        original = '[mcp_servers.baton_greg]\ncommand = "/usr/bin/python3"\ndefault_tools_approval_mode = "auto"\n'
        self.config.write_text(original)
        with self.assertRaisesRegex(ValueError, "differs"):
            install(self.config, self.script, sys.executable)
        self.assertEqual(self.config.read_text(), original)

    def test_refuses_overwrite_existing_server(self):
        self.config.parent.mkdir()
        original = "[mcp_servers.baton_greg]\ncommand = \"other\"\n"
        self.config.write_text(original)
        with self.assertRaisesRegex(ValueError, "differs"):
            install(self.config, self.script, sys.executable)
        self.assertEqual(self.config.read_text(), original)

    def test_rejects_config_symlink(self):
        self.config.parent.mkdir()
        target = self.root / "target.toml"
        target.write_text("model = \"gpt-6\"\n")
        self.config.symlink_to(target)
        with self.assertRaisesRegex(ValueError, "symlink"):
            install(self.config, self.script, sys.executable)
        self.assertEqual(target.read_text(), 'model = "gpt-6"\n')

    def test_preserves_invalid_config_unmodified(self):
        self.config.parent.mkdir()
        self.config.write_text("model = [ invalid")
        with self.assertRaises(tomllib.TOMLDecodeError):
            install(self.config, self.script, sys.executable)
        self.assertEqual(self.config.read_text(), "model = [ invalid")


@unittest.skipIf(os.geteuid() == 0, "Baton Core must not run as root")
class DesktopMcpEndToEndTests(unittest.TestCase):
    def test_actual_core_write_and_readback_via_mcp(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            token_file = root / "private-token"
            core = start_local_core(port=0, token_file=token_file)
            try:
                endpoint = f"http://127.0.0.1:{core.server_port}/v1/exec"
                original_exec = baton_core_client.execute_on_greg
                def via_core(argv, cwd, timeout):
                    return original_exec(argv, cwd, timeout, token_file=token_file)
                with patch.object(baton_core_client, "CORE_URL", endpoint):
                    with patch("baton_mcp_stdio.execute_on_greg", side_effect=via_core), patch("baton_mcp_stdio.ui_lease_active", return_value=True):
                        def invoke(command):
                            result = handle({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                                             "params": {"name": "greg_exec",
                                                        "arguments": {"argv": [sys.executable, "-c", command],
                                                                      "cwd": str(root), "timeout": 10}}})
                            self.assertFalse(result["result"]["isError"], result)
                            return json.loads(result["result"]["content"][0]["text"])
                        written = invoke("from pathlib import Path; Path('proof.txt').write_text('BATON-MCP-WRITE-OK')")
                        self.assertEqual(written["exit_code"], 0)
                        read = invoke("from pathlib import Path; print(Path('proof.txt').read_text())")
                        self.assertEqual(read["output"].strip(), "BATON-MCP-WRITE-OK")
                        self.assertEqual((root / "proof.txt").read_text(), "BATON-MCP-WRITE-OK")
            finally:
                stop_local_core(core)


if __name__ == "__main__":
    unittest.main()
