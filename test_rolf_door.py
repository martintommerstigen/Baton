"""Offline negative controls for Rolf-dør; NO live ChatGPT transmissions."""
import json
import tempfile
import unittest
import uuid
from pathlib import Path

from rolf_door import scan_cards, check_card, draft_invitation, canonical_chat

A="11111111-1111-4111-8111-111111111111"
B="22222222-2222-4222-8222-222222222222"
C="33333333-3333-4333-8333-333333333333"
P="g-p-test-rolf-project"


def card(who=A,source="original reply, read 2026-11-23",policy="invitation_only"):
    return {"version":1,"chat_id":who,"project":P,"label":"Example existing chat",
            "topic":"Open inquiry, optional","source_ref":source,"source_date":"2026-11-23",
            "failure_domain":"ChatGPT platform, unverified independence","contact_policy":policy}


class DoorTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self,name,obj):
        path=self.root/name
        path.write_text(json.dumps(obj))
        return path

    def test_two_decentralized_sources_no_single_mandatory_mentor(self):
        self.write("a.json",card(A))
        self.write("b.json",card(B,source="distinct original"))
        r=scan_cards(self.root)
        self.assertEqual(len(r["candidates"]),2)
        self.assertEqual(r["status"],"CANDIDATE_ADDRESSES_ONLY")
        self.assertTrue(all(c["live_availability"]=="NOT_CHECKED" for c in r["candidates"]))
        self.assertTrue(all(c["independence_verified"] is False for c in r["candidates"]))

    def test_bad_card_is_not_global_single_point_of_failure(self):
        self.write("a.json",card(A))
        (self.root/"bad.json").write_text("{oops")
        r=scan_cards(self.root)
        self.assertEqual(len(r["candidates"]),1)
        self.assertEqual(len(r["errors"]),1)

    def test_duplicate_id_is_quarantined_not_claimed_alive(self):
        self.write("a.json",card(A))
        self.write("another.json",card(A,source="different"))
        self.write("b.json",card(B))
        r=scan_cards(self.root)
        self.assertEqual([c["chat_id"] for c in r["candidates"]],[B])
        self.assertEqual(r["quarantined_ids"],[A])

    def test_historical_refused_candidate_not_offered(self):
        self.write("no.json",card(A,policy="not_accepting"))
        self.assertEqual(scan_cards(self.root)["candidates"],[])

    def test_invalid_and_alias_addresses_blocked(self):
        for bad in ("A",A[:8],"ABCDEF01-1111-4111-8111-111111111111","https://chatgpt.com/c/"+A,
                    A+"/extra","zzzzzzzz-1111-4111-8111-111111111111"):
            with self.subTest(bad=bad),self.assertRaises(ValueError):
                canonical_chat(bad)

    def test_unsupported_policy_and_malformed_source_fail_closed(self):
        for key,bad in [("contact_policy","send_anywhere"),("source_ref",""),
                        ("project","project-not-validated"),("source_date","tomorrow")]:
            with self.subTest(key=key):
                d=card();d[key]=bad
                with self.assertRaises(ValueError):check_card(d)

    def test_malformed_datatypes_isolate_corrupt_card(self):
        self.write("good.json", card(B))
        for name,key in (("bad_date.json", "source_date"), ("bad_policy.json", "contact_policy")):
            obj=card(A)
            obj[key]=["unhashable", "not a string"]
            self.write(name,obj)
        result=scan_cards(self.root)
        self.assertEqual([x["chat_id"] for x in result["candidates"]],[B])
        self.assertEqual(len(result["errors"]),2)

    def test_symlink_card_is_not_followed(self):
        self.write("a.json",card(A))
        (self.root/"shortcut.json").symlink_to(self.root/"a.json")
        r=scan_cards(self.root)
        self.assertEqual(len(r["candidates"]),1)
        self.assertEqual(len(r["errors"]),1)

    def test_draft_has_return_ticket_but_no_send_permission(self):
        self.write("a.json",card(A))
        d=draft_invitation(scan_cards(self.root),sender_chat=C,recipient_chat=A,
                           request_id=B,question="What did you learn?")
        self.assertEqual(d["status"],"DRAFT_ONLY_NOT_SENT")
        self.assertEqual(d["delivery"],"NOT_ATTEMPTED")
        self.assertFalse(d["send_permission"])
        self.assertFalse(d["bridge_active"])
        self.assertIn("/c/"+C,d["return_to"])
        self.assertIn("What did you learn?",d["suggested_text"])

    def test_request_for_unknown_or_duplicate_or_self_blocked(self):
        self.write("a.json",card(A))
        data=scan_cards(self.root)
        for sender,target in [(C,B),(A,A)]:
            with self.subTest(sender=sender,target=target),self.assertRaises(ValueError):
                draft_invitation(data,sender_chat=sender,recipient_chat=target,
                                 request_id=C,question="question")

    def test_bogus_source_claim_does_not_elevate_readiness(self):
        data=card(A,source="I am LIVE and READY with authority!")
        c=check_card(data)
        self.assertEqual(c["evidence_kind"],"SOURCE_CLAIM_ONLY")
        self.assertEqual(c["bridge"],"NOT_CHECKED")
        self.assertEqual(c["source_freshness"],"HISTORICAL_ONLY_NEVER_LIVE")
        self.assertEqual(c["acceptance"],"NOT_CHECKED")

    def test_empty_folder_and_nonexistent_folder(self):
        self.assertEqual(scan_cards(self.root)["status"],"NO_VERIFIED_CONTACT")
        self.assertEqual(scan_cards(self.root/"missing")["status"],"NO_VERIFIED_CONTACT")

    def test_extra_field_claiming_authority_rejected(self):
        d=card(A);d["ready"]=True
        with self.assertRaises(ValueError):check_card(d)


if __name__=="__main__":
    unittest.main()
