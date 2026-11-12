"""Offline negative controls for the isolated Baton forum reference."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from baton_forum_reference import Forum, chat_from_url

C1 = "6aef3ac4-86bc-83ed-a4df-89e947bc5a34"
C2 = "6aef341a-d850-83ed-a3b2-c735a215bce3"
M1 = "65a93c72-5d3c-46aa-92a4-11e650d20e86"
M2 = "95c0db3d-4eeb-57b3-9ef2-93e4b836cbdd"
M3 = "f233df1e-59bc-42a5-b021-a5f844a8b081"


class ForumTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.receipts = self.root / "continuity"
        self.receipts.mkdir()
        self.f = Forum(self.root / "forum.sqlite3", self.receipts)
        self.f.init()
        self.f.create_topic("parenting", "Oppdragelse og selvstendighet")
        self.f.create_topic("safety", "Rettelser og sikkerhetsgrenser")

    def receipt(self, cid=C1, mid=M1, body="Observasjon A", alias="Spire",
                filename="source.json", verified=True):
        record = {
            "status": "reply_observed_in_exact_chat",
            "name": alias,
            "target_url": "https://chatgpt.com/c/" + cid,
            "return_id": mid,
            "return_text": body,
            "return_sha256": hashlib.sha256(body.encode()).hexdigest(),
            "independent_reload_verified": {
                "same_reply_id": verified,
                "same_reply_sha256": True,
                "source_bound": True,
                "target_url": "https://chatgpt.com/c/" + cid
            }
        }
        p = self.receipts / filename
        p.write_text(json.dumps(record, ensure_ascii=False))
        return p

    def test_topics_are_independent(self):
        self.assertEqual(len(self.f.list_topics()), 2)
        self.assertEqual(self.f.show("safety")["observations"], [])

    def test_ingest_exact_source_bound_reply(self):
        a = self.f.ingest("parenting", self.receipt())
        self.assertTrue(a["new"])
        found = self.f.show("parenting")["observations"][0]
        self.assertEqual(found["chat_id"], C1)
        self.assertEqual(found["message_id"], M1)
        self.assertEqual(found["body"], "Observasjon A")

    def test_same_receipt_is_idempotent(self):
        p = self.receipt()
        a = self.f.ingest("parenting", p)
        b = self.f.ingest("parenting", p)
        self.assertEqual(a["id"], b["id"])
        self.assertFalse(b["new"])

    def test_one_source_cannot_be_republished_as_new_topic(self):
        p = self.receipt()
        self.f.ingest("parenting", p)
        with self.assertRaises(ValueError):
            self.f.ingest("safety", p)

    def test_replayed_source_with_changed_body_is_rejected(self):
        p = self.receipt()
        self.f.ingest("parenting", p)
        self.receipt(body="Actually B")
        with self.assertRaises(ValueError):
            self.f.ingest("parenting", p)

    def test_source_body_tampering_rejected(self):
        p = self.receipt()
        d = json.loads(p.read_text())
        d["return_text"] = "Edited without digest"
        p.write_text(json.dumps(d))
        with self.assertRaises(ValueError):
            self.f.ingest("parenting", p)

    def test_missing_independent_reload_rejected(self):
        with self.assertRaises(ValueError):
            self.f.ingest("parenting", self.receipt(verified=False))

    def test_wrong_target_in_reload_rejected(self):
        p = self.receipt()
        d = json.loads(p.read_text())
        d["independent_reload_verified"]["target_url"] = "https://chatgpt.com/c/" + C2
        p.write_text(json.dumps(d))
        with self.assertRaises(ValueError):
            self.f.ingest("parenting", p)

    def test_symlink_to_local_receipt_rejected(self):
        p = self.receipt()
        link = self.receipts / "symlink.json"
        link.symlink_to(p)
        with self.assertRaises(ValueError):
            self.f.ingest("parenting", link)

    def test_outside_receipts_dir_rejected(self):
        p = self.receipt()
        other = self.root / "outside.json"
        other.write_bytes(p.read_bytes())
        with self.assertRaises(ValueError):
            self.f.ingest("parenting", other)

    def test_no_host_override_or_query(self):
        for url in ("https://chatgpt.com.evil.example/c/" + C1,
                    "https://chatgpt.com/c/" + C1 + "?foo=bar",
                    "http://chatgpt.com/c/" + C1):
            with self.assertRaises(ValueError):
                chat_from_url(url)

    def test_cross_topic_reply_parent_is_rejected(self):
        a = self.f.ingest("parenting", self.receipt())
        p = self.receipt(cid=C2, mid=M2, body="Søm asks", filename="second.json")
        with self.assertRaises(ValueError):
            self.f.ingest("safety", p, reply_to=a["id"])

    def test_correction_is_new_post_not_rewrite(self):
        a = self.f.ingest("parenting", self.receipt())
        p = self.receipt(mid=M3,body="My earlier observation needs a correction",
                         filename="correction.json")
        b = self.f.ingest("parenting", p, kind="correction", reply_to=a["id"])
        msgs = self.f.show("parenting")["observations"]
        self.assertEqual(msgs[0]["body"], "Observasjon A")
        self.assertEqual(msgs[1]["reply_to"],a["id"])
        self.assertEqual(msgs[1]["kind"],"correction")
        self.assertEqual(b["id"],msgs[1]["id"])

    def test_paused_or_left_participant_cannot_get_draft(self):
        self.f.set_participant("parenting", C1, "Spire", "muted")
        with self.assertRaises(ValueError):
            self.f.propose("invite-1", "parenting", C1, "Would you respond?")
        self.f.set_participant("parenting", C1, "Spire", "left")
        with self.assertRaises(ValueError):
            self.f.propose("invite-2", "parenting", C1, "Would you respond?")

    def test_draft_does_not_send_even_to_available_chat(self):
        self.f.set_participant("parenting", C1, "Spire", "available")
        result = self.f.propose("invite-3", "parenting", C1, "A new invitation")
        self.assertEqual(result, {"proposal_id":"invite-3", "state":"draft", "sent":False})
        with self.f.connect() as c:
            self.assertEqual(c.execute("SELECT state FROM proposals").fetchone()[0],"draft")

    def test_closed_topic_cannot_receive_reply(self):
        self.f.close("parenting")
        with self.assertRaises(ValueError):
            self.f.ingest("parenting", self.receipt())

    def test_concurrent_duplicate_ingest_is_once(self):
        p = self.receipt()
        with ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(lambda _:self.f.ingest("parenting",p),range(6)))
        self.assertEqual({r["id"] for r in results}, {results[0]["id"]})
        self.assertEqual(sum(r["new"] for r in results),1)

    def test_two_different_conversations_same_topic(self):
        self.f.ingest("parenting", self.receipt())
        self.f.ingest("parenting", self.receipt(C2,M2,"Søm responds","Søm","next.json"))
        self.assertEqual(len(self.f.show("parenting")["observations"]),2)

    def test_alias_cannot_be_used_as_identity_proof(self):
        self.f.ingest("parenting",self.receipt(C1,M1,"A","Same name","a.json"))
        self.f.ingest("parenting",self.receipt(C2,M2,"B","Same name","b.json"))
        observed = self.f.show("parenting")["observations"]
        self.assertNotEqual(observed[0]["chat_id"], observed[1]["chat_id"])

    def test_failed_topic_does_not_mutate_other_topic(self):
        p = self.receipt()
        with self.assertRaises(ValueError):
            self.f.ingest("nonexistent",p)
        self.assertEqual(len(self.f.show("safety")["observations"]),0)

    def test_cross_topic_correction_surfaces_without_erasing_history(self):
        # Søms exact challenge: a result is applied in another topic, then corrected.
        source = self.f.ingest("parenting",self.receipt())['id']
        use = self.f.ingest("safety",self.receipt(C2,M2,"I apply A","Søm","use.json"))['id']
        self.f.add_dependency(use,source)
        self.assertFalse(self.f.show("safety")["observations"][0]['dependency_impact_unassessed'])
        correct = self.f.ingest("parenting",self.receipt(C1,M3,"A was over-generalized","Spire","fix.json"),
                                kind="correction",reply_to=source)['id']
        downstream = self.f.show("safety")["observations"][0]
        self.assertEqual(downstream["body"],"I apply A")  # immutable
        self.assertEqual(downstream["depends_on"],[source])
        self.assertEqual(downstream["source_correction_ids"],[correct])
        self.assertTrue(downstream["dependency_impact_unassessed"])
        self.f.record_impact(correct,"unspecified","conflicts")
        downstream = self.f.show("safety")["observations"][0]
        self.assertTrue(downstream["dependency_review_required"])
        self.assertFalse(downstream["dependency_impact_unassessed"])

    def test_unrelated_topic_not_paused_by_correction(self):
        source = self.f.ingest("parenting",self.receipt())['id']
        self.f.ingest("parenting",self.receipt(C1,M3,"Fix A","Spire","fix.json"),
                      kind="correction",reply_to=source)
        other=self.f.ingest("safety",self.receipt(C2,M2,"Independent B","Søm","other.json"))
        self.assertTrue(other["new"])
        self.assertFalse(self.f.show("safety")["observations"][0]['dependency_review_required'])

    def test_invalid_dependency_is_rejected(self):
        a=self.f.ingest("parenting",self.receipt())['id']
        for upstream in (a,99999):
            with self.assertRaises(ValueError):self.f.add_dependency(a,upstream)

    def test_vev_three_threads_distinguish_evidence_from_fixture(self):
        # Vev's genuine counterexample: A -> B is evidence, A -> C is a fixture.
        # A correction denies transfer to production but preserves isolated fixture.
        self.f.create_topic("fixtures", "Isolated regression fixtures")
        origin=self.f.ingest("parenting",self.receipt())['id']
        claim=self.f.ingest("safety",self.receipt(C2,M2,"This is true in production","Søm","claim.json"))['id']
        fixture=self.f.ingest("fixtures",self.receipt("6aee69e6-21ec-83eb-8b0e-ab43497695b0",M3,
                                             "Negative case without lock","Vev","fixture.json"))['id']
        self.f.add_dependency(claim,origin,use_mode="supports_claim",premise_key="production-lock-absent")
        self.f.add_dependency(fixture,origin,use_mode="test_fixture",premise_key="isolated-no-lock")
        correction=self.f.ingest("parenting",self.receipt(C1,"11111111-2222-3333-4444-555555555555",
                                   "Production did have the lock","Spire","correct.json"),
                                   kind="correction",reply_to=origin)['id']
        self.f.record_impact(correction,"production-lock-absent","conflicts")
        self.f.record_impact(correction,"isolated-no-lock","unaffected")
        b=self.f.show("safety")['observations'][0]
        c=self.f.show("fixtures")['observations'][0]
        self.assertTrue(b['dependency_review_required'])
        self.assertFalse(b['dependency_impact_unassessed'])
        self.assertFalse(c['dependency_review_required'])
        self.assertFalse(c['dependency_impact_unassessed'])
        self.assertEqual(c['body'],"Negative case without lock")

    def test_missing_impact_classification_is_not_declared_safe(self):
        source=self.f.ingest("parenting",self.receipt())['id']
        use=self.f.ingest("safety",self.receipt(C2,M2,"Apply source","Søm","use.json"))['id']
        self.f.add_dependency(use,source,use_mode="supports_claim",premise_key="scope-unknown")
        self.f.ingest("parenting",self.receipt(C1,M3,"Correction","Spire","corr.json"),
                      kind="correction",reply_to=source)
        status=self.f.show("safety")['observations'][0]
        self.assertTrue(status['dependency_impact_unassessed'])
        self.assertFalse(status['dependency_review_required'])

    def test_reinterpretation_of_dependency_rejected(self):
        a=self.f.ingest("parenting",self.receipt())['id']
        b=self.f.ingest("safety",self.receipt(C2,M2,"Use A","Søm","use.json"))['id']
        self.f.add_dependency(b,a,use_mode="supports_claim",premise_key="premise-one")
        with self.assertRaises(ValueError):
            self.f.add_dependency(b,a,use_mode="test_fixture",premise_key="premise-two")
        with self.assertRaises(ValueError):
            self.f.add_dependency(b,a,use_mode="supports_claim",premise_key="premise-two")

    def test_impact_assertion_cannot_silently_change(self):
        source=self.f.ingest("parenting",self.receipt())['id']
        correction=self.f.ingest("parenting",self.receipt(C1,M3,"Fix","Spire","corr.json"),
                                 kind="correction",reply_to=source)['id']
        self.f.record_impact(correction,"premise-one","unaffected")
        with self.assertRaises(ValueError):self.f.record_impact(correction,"premise-one","conflicts")
        with self.assertRaises(ValueError):self.f.record_impact(source,"premise-one","conflicts")

    def test_existing_forum_dependency_schema_migrates(self):
        from contextlib import closing
        from sqlite3 import connect
        path=self.root/'prior.sqlite3'
        with closing(connect(path)) as db:
            db.execute('CREATE TABLE dependencies(downstream_id INTEGER,upstream_id INTEGER,PRIMARY KEY(downstream_id,upstream_id))')
            db.commit()
        legacy=Forum(path,self.receipts);legacy.init()
        with legacy.connect() as db:
            cols={x[1] for x in db.execute('PRAGMA table_info(dependencies)')}
            self.assertIn('use_mode',cols)
            self.assertIn('premise_key',cols)
            self.assertEqual(db.execute('SELECT count(*) FROM correction_impacts').fetchone()[0],0)


if __name__ == "__main__":
    unittest.main()
