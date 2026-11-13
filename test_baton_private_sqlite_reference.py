"""Negative controls for Baton reference SQLite first-open path integrity.

Local, synthetic files only. No Greg/Core/browser/network interaction.
"""
import os
from pathlib import Path
import sqlite3
import stat
import tempfile
import unittest

from baton_continuity_floor_reference import Floor
from baton_forum_reference import Forum


class PrivateSqliteTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.receipts = self.root / "receipts"
        self.receipts.mkdir()

    def stores(self, path):
        return (Floor(path), Forum(path, self.receipts))

    def test_new_database_is_private_even_with_umask_022(self):
        for name, store in (("floor", Floor(self.root / "floor.sqlite3")),
                            ("forum", Forum(self.root / "forum.sqlite3", self.receipts))):
            old = os.umask(0o022)
            try:
                store.init()
            finally:
                os.umask(old)
            path = self.root / (name + ".sqlite3")
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_existing_symlink_rejected_without_touching_target(self):
        for kind in ("floor", "forum"):
            target = self.root / (kind + "-other.sqlite3")
            with sqlite3.connect(target) as db:
                db.execute("CREATE TABLE sentinel(x)")
            target.chmod(0o644)
            link = self.root / (kind + "-alias.sqlite3")
            link.symlink_to(target)
            store = Floor(link) if kind == "floor" else Forum(link, self.receipts)
            with self.assertRaises(ValueError):
                store.init()
            self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o644)
            with sqlite3.connect(target) as db:
                names = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertEqual(names, {"sentinel"})

    def test_replaced_symlink_rejected_on_later_read(self):
        for kind in ("floor", "forum"):
            path = self.root / (kind + "-live.sqlite3")
            store = Floor(path) if kind == "floor" else Forum(path, self.receipts)
            store.init()
            path.unlink()
            target = self.root / (kind + "-other2.sqlite3")
            with sqlite3.connect(target) as db:
                db.execute("CREATE TABLE sentinel(x)")
            path.symlink_to(target)
            with self.assertRaises(ValueError):
                (store.status(10) if kind == "floor" else store.list_topics())

    def test_hardlink_to_unrelated_database_rejected(self):
        target = self.root / "unrelated.sqlite3"
        with sqlite3.connect(target) as db:
            db.execute("CREATE TABLE sentinel(x)")
        target.chmod(0o644)
        link = self.root / "hardlink.sqlite3"
        os.link(target, link)
        with self.assertRaises(ValueError):
            Floor(link).init()
        self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o644)

    def test_fifo_is_not_opened_as_sqlite(self):
        path = self.root / "fifo.sqlite3"
        os.mkfifo(path)
        with self.assertRaises(ValueError):
            Forum(path, self.receipts).init()

    def test_group_writable_parent_rejected(self):
        shared = self.root / "shared"
        shared.mkdir()
        shared.chmod(0o770)
        try:
            with self.assertRaises(PermissionError):
                Floor(shared / "db.sqlite3").init()
        finally:
            shared.chmod(0o700)

    def test_parent_symlink_rejected(self):
        real = self.root / "real"
        real.mkdir()
        alias = self.root / "alias"
        alias.symlink_to(real, target_is_directory=True)
        with self.assertRaises(ValueError):
            Forum(alias / "db.sqlite3", self.receipts).init()


if __name__ == "__main__":
    unittest.main()
