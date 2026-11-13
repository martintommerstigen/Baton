import tempfile
from pathlib import Path
import subprocess
import unittest

from baton_safe_update import UpdateError, safe_fast_forward


class SafeUpdateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.remote = self.base / "remote.git"
        subprocess.run(["git", "init", "--bare", "-q", str(self.remote)], check=True)

        seed = self.base / "seed"
        subprocess.run(["git", "init", "-q", "-b", "feature/test", str(seed)], check=True)
        subprocess.run(["git", "-C", str(seed), "config", "user.name", "Test"], check=True)
        subprocess.run(["git", "-C", str(seed), "config", "user.email", "test@example.invalid"], check=True)
        (seed / "file.txt").write_text("one\n")
        subprocess.run(["git", "-C", str(seed), "add", "file.txt"], check=True)
        subprocess.run(["git", "-C", str(seed), "commit", "-qm", "one"], check=True)
        subprocess.run(["git", "-C", str(seed), "remote", "add", "origin", str(self.remote)], check=True)
        subprocess.run(["git", "-C", str(seed), "push", "-q", "-u", "origin", "feature/test"], check=True)

        self.work = self.base / "work"
        subprocess.run(
            ["git", "clone", "-q", "-b", "feature/test", str(self.remote), str(self.work)],
            check=True,
        )
        # The production policy expects GitHub HTTPS. Tests replace the local
        # transport URL only at the final invocation by temporarily using the
        # exact remote path through a policy-neutral helper below.
        self.seed = seed

    def invoke_local(self):
        # Preserve all update invariants while avoiding network access in tests.
        # safe_fast_forward's origin policy is intentionally production-only,
        # so monkeypatch the origin string to a GitHub-shaped local rewrite.
        expected = "https://github.com/example/Baton.git"
        subprocess.run(["git", "-C", str(self.work), "remote", "set-url", "origin", expected], check=True)
        subprocess.run(
            ["git", "-C", str(self.work), "config", f"url.{self.remote.as_posix()}.insteadOf", expected],
            check=True,
        )
        return safe_fast_forward(
            self.work, expected_origin=expected, expected_branch="feature/test"
        )

    def push_change(self, text="two\n"):
        (self.seed / "file.txt").write_text(text)
        subprocess.run(["git", "-C", str(self.seed), "add", "file.txt"], check=True)
        subprocess.run(["git", "-C", str(self.seed), "commit", "-qm", "change"], check=True)
        subprocess.run(["git", "-C", str(self.seed), "push", "-q", "origin", "feature/test"], check=True)

    def test_fast_forwards_clean_checkout(self):
        self.push_change()
        result = self.invoke_local()
        self.assertEqual(result["state"], "updated")
        self.assertEqual((self.work / "file.txt").read_text(), "two\n")

    def test_already_current_is_noop(self):
        result = self.invoke_local()
        self.assertEqual(result["state"], "already-current")

    def test_dirty_checkout_is_rejected(self):
        (self.work / "local.txt").write_text("do not overwrite\n")
        with self.assertRaisesRegex(UpdateError, "local changes"):
            self.invoke_local()

    def test_wrong_branch_is_rejected(self):
        expected = "https://github.com/example/Baton.git"
        subprocess.run(["git", "-C", str(self.work), "remote", "set-url", "origin", expected], check=True)
        with self.assertRaisesRegex(UpdateError, "branch mismatch"):
            safe_fast_forward(
                self.work, expected_origin=expected, expected_branch="feature/other"
            )

    def test_symlink_checkout_is_rejected(self):
        link = self.base / "linked"
        link.symlink_to(self.work, target_is_directory=True)
        with self.assertRaisesRegex(UpdateError, "symlink"):
            safe_fast_forward(
                link,
                expected_origin="https://github.com/example/Baton.git",
                expected_branch="feature/test",
            )


if __name__ == "__main__":
    unittest.main()
