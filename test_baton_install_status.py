from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from baton_install_status import inspect_installation


class InstallationInspectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.repo = self.home / "checkout"
        (self.repo / ".git").mkdir(parents=True)
        (self.repo / "baton_mcp_stdio.py").write_text("# MCP")
        (self.repo / "run_baton_direct.sh").write_text("#!/bin/bash\n")
        self.commands = []

    def runner(self, argv, **kwargs):
        self.commands.append(argv)
        if argv[0] == "systemctl":
            return SimpleNamespace(returncode=0, stdout="active\n")
        if argv[-2:] == ["rev-parse", "HEAD"]:
            return SimpleNamespace(returncode=0, stdout="a" * 40 + "\n")
        if argv[-3:] == ["rev-parse", "--abbrev-ref", "HEAD"]:
            return SimpleNamespace(returncode=0, stdout="feature/evening-local-terminal-2026-11-10\n")
        if argv[-2:] == ["status", "--porcelain"]:
            return SimpleNamespace(returncode=0, stdout="")
        return SimpleNamespace(returncode=1, stdout="")

    def inspect(self):
        return inspect_installation(root=self.repo, home=self.home,
                                    runner=self.runner, tcp_check=lambda: True,
                                    lease_check=lambda: True, which=lambda _: "/usr/bin/chatgpt")

    def test_report_is_readonly_and_separates_observation_from_auth(self):
        token = self.home / ".config/baton/local-api-token"
        token.parent.mkdir(parents=True)
        token.write_text("DO-NOT-DISCLOSE-THIS-SECRET")
        token.chmod(0o600)
        config = self.home / ".codex/config.toml"
        config.parent.mkdir()
        config.write_text(
            "[mcp_servers.baton_greg]\n"
            "enabled=true\n"
            "args=[\""+str(self.repo / "baton_mcp_stdio.py")+"\"]\n"
            "[private]\npassword=\"HIDDEN-SECRET\"\n"
        )
        launch = self.home / ".local/share/applications/baton.desktop"
        launch.parent.mkdir(parents=True)
        launch.write_text("[Desktop Entry]\nName=Baton\nExec=/usr/bin/bash "+
                          str(self.repo / "run_baton_direct.sh")+"\n")
        result = self.inspect()
        self.assertEqual(result["codex_mcp_config_state"], "registered-for-codex")
        self.assertEqual(result["branch"], "feature/evening-local-terminal-2026-11-10")
        self.assertTrue(result["clean_worktree"])
        self.assertTrue(result["core_token_private_mode_only"])
        self.assertTrue(result["core_service_active_unverified"])
        self.assertTrue(result["core_port_open_unverified"])
        self.assertTrue(result["baton_desktop_entry_matches"])
        self.assertFalse(result["existing_chat_wake_verified"])
        self.assertNotIn("DO-NOT-DISCLOSE", str(result))
        self.assertNotIn("HIDDEN-SECRET", str(result))
        self.assertEqual(token.read_text(), "DO-NOT-DISCLOSE-THIS-SECRET")
        self.assertEqual(config.read_text().count("HIDDEN-SECRET"), 1)

    def test_no_token_or_code_config_and_symlink_refusal(self):
        config = self.home / ".codex/config.toml"
        config.parent.mkdir(parents=True)
        target = self.home / "another"
        target.write_text("SECRET-CONTENT")
        config.symlink_to(target)
        result = self.inspect()
        self.assertEqual(result["codex_mcp_config_state"], "symlink-refused")
        self.assertFalse(result["core_token_private_mode_only"])
        self.assertFalse(result["baton_desktop_entry_matches"])
        self.assertNotIn("SECRET-CONTENT", str(result))

    def test_refuses_world_readable_token_mode(self):
        token = self.home / ".config/baton/local-api-token"
        token.parent.mkdir(parents=True)
        token.write_text("never-read")
        token.chmod(0o644)
        self.assertFalse(self.inspect()["core_token_private_mode_only"])

    def test_invalid_toml_fails_readonly(self):
        config = self.home / ".codex/config.toml"
        config.parent.mkdir(parents=True)
        config.write_text("not = [ invalid")
        self.assertEqual(self.inspect()["codex_mcp_config_state"], "invalid")


if __name__ == "__main__":
    unittest.main()
