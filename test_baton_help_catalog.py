"""Negative controls and revision tests for dynamic native Baton help."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import os
import sqlite3
import tempfile
import unittest

from baton_help_catalog import HelpCatalog, DEFAULT_ARTICLES


class DynamicHelpTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)
        self.store=HelpCatalog(self.root/"catalog.sqlite3")
        self.store.initialize()

    def sample(self):
        return self.store.add("example-howto","howto","Bruk Baton riktig",
            "Åpne først riktig samtale.\nIkke gjensend blindt.",
            "Testgrunnlag 123","Startpunkt")

    def proposal(self):
        return self.store.propose("example-howto",1,"Bruk Baton trygt",
            "Kontroller effektgrensen. Ikke gjensend uten bevis.",
            "Korrigert av Vev ID 123","En eldre generalisering var for bred")

    def test_seed_creates_both_categories(self):
        count=self.store.seed()
        self.assertEqual(count,len(DEFAULT_ARTICLES))
        self.assertGreaterEqual(len(self.store.list("faq")),5)
        self.assertGreaterEqual(len(self.store.list("howto")),4)

    def test_seed_is_idempotent_and_never_reverts_a_correction(self):
        self.store.seed()
        row=self.store.get("send-and-verify")
        pid=self.store.propose(row["slug"],1,row["title"],row["body"]+"\nNy presisering.",
                               "Ny kilde","Utvidet avgrensning")
        self.assertTrue(self.store.apply(pid,1)["applied"])
        self.assertEqual(self.store.seed(),0)
        self.assertIn("Ny presisering.",self.store.get("send-and-verify")["body"])

    def test_add_new_article_appears_in_dynamic_list(self):
        self.sample()
        rows=self.store.list("howto")
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]["slug"],"example-howto")

    def test_search_looks_in_current_title_and_body(self):
        self.sample()
        self.assertEqual(len(self.store.list(query="GJENSEND")),1)
        self.assertEqual(len(self.store.list(query="does-not-exist")),0)

    def test_search_escape_cannot_match_everything(self):
        self.sample()
        self.assertEqual(self.store.list(query="%"),[])
        self.assertEqual(self.store.list(query="_"),[])

    def test_proposal_does_not_change_live_article(self):
        self.sample()
        pid=self.proposal()
        row=self.store.get("example-howto")
        self.assertEqual(row["revision"],1)
        self.assertEqual(row["status"],"challenged")
        self.assertTrue(any(p["id"]==pid for p in row["proposals"]))
        self.assertNotIn("Kontroller effektgrensen",row["body"])

    def test_explicit_approval_appends_revision_with_source(self):
        self.sample()
        pid=self.proposal()
        result=self.store.apply(pid,1)
        self.assertTrue(result["applied"])
        row=self.store.get("example-howto")
        self.assertEqual(row["revision"],2)
        self.assertEqual(row["status"],"current")
        self.assertIn("Kontroller effektgrensen",row["body"])
        self.assertEqual(len(row["history"]),2)
        self.assertEqual(row["history"][1]["revision"],1)
        self.assertIn("Vev",row["source"])

    def test_double_apply_cannot_revive_old_plan(self):
        self.sample()
        pid=self.proposal()
        self.store.apply(pid,1)
        with self.assertRaises(ValueError):
            self.store.apply(pid,1)

    def test_stale_proposals_are_not_applied(self):
        self.sample()
        a=self.proposal()
        b=self.store.propose("example-howto",1,"Alternative",
            "Oppgi ekstra kilde og behold tidligere korrigering.",
            "Lodd kilde","Alternativ")
        self.assertTrue(self.store.apply(a,1)["applied"])
        with self.assertRaises(ValueError):
            self.store.apply(b,1)
        self.assertEqual(self.store.get("example-howto")["revision"],2)

    def test_competing_approvals_only_one_commits(self):
        self.sample()
        a=self.proposal()
        b=self.store.propose("example-howto",1,"Alternative",
            "Alternativ presisering med en annen hypotese.",
            "Søm kilde","Konkurrerende forslag")
        def apply(pid):
            try:return self.store.apply(pid,1)["applied"]
            except ValueError:return False
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes=list(pool.map(apply,(a,b)))
        self.assertEqual(sum(outcomes),1)
        self.assertEqual(self.store.get("example-howto")["revision"],2)

    def test_withdraw_restores_current_if_all_objections_withdrawn(self):
        self.sample()
        pid=self.proposal()
        self.assertTrue(self.store.withdraw(pid))
        self.assertEqual(self.store.get("example-howto")["status"],"current")
        self.assertEqual(self.store.get("example-howto")["revision"],1)

    def test_one_of_two_proposals_keeps_challenged_status(self):
        self.sample()
        a=self.proposal()
        b=self.store.propose("example-howto",1,"Other",
             "New concrete counterexample is not dismissed.",
             "Another source","Alternative correction")
        self.store.withdraw(a)
        self.assertEqual(self.store.get("example-howto")["status"],"challenged")
        self.assertTrue(self.store.withdraw(b))

    def test_rejected_missing_source_or_reason(self):
        self.sample()
        with self.assertRaises(ValueError):
            self.store.propose("example-howto",1,"Title","Document"," ","Because")
        with self.assertRaises(ValueError):
            self.store.propose("example-howto",1,"Title","Document","Source"," ")

    def test_wrong_category_and_slugs_are_rejected(self):
        with self.assertRaises(ValueError):
            self.store.add("../evil","faq","Title","Answer","Source","Reason")
        with self.assertRaises(ValueError):
            self.store.add("okay-title","system-policy","Title","Answer","Source","Reason")

    def test_no_sql_interpolation_in_search(self):
        self.sample()
        self.assertEqual(self.store.list(query="';DROP TABLE articles;--"),[])
        self.assertIsNotNone(self.store.get("example-howto"))

    def test_symbolic_link_database_rejected(self):
        target=self.root/"safe.sqlite3"
        target.touch()
        evil=self.root/"linked.sqlite3"
        evil.symlink_to(target)
        with self.assertRaises(ValueError):
            HelpCatalog(evil).initialize()

    def test_seed_has_no_send_or_core_writes(self):
        self.store.seed()
        self.assertFalse((self.root/"PAUSE_UI_WRITES").exists())
        self.assertEqual([p.name for p in self.root.iterdir()],["catalog.sqlite3"])

    def test_article_title_history_tracks_multiple_revisions(self):
        self.sample()
        p1=self.proposal()
        self.store.apply(p1,1)
        p2=self.store.propose("example-howto",2,"Bruk Baton nøkternt",
            "Kun én mulig tolkning; kontroller konkret.",
            "Søm og Spire kilde","Ny motprøve")
        self.store.apply(p2,2)
        row=self.store.get("example-howto")
        self.assertEqual(row["revision"],3)
        self.assertEqual([r["revision"] for r in row["history"]],[3,2,1])


if __name__=="__main__":
    unittest.main()
