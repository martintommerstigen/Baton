"""Deterministic, offline controls for dynamic non-authoritative learning lists."""
from concurrent.futures import ThreadPoolExecutor
import sqlite3
from pathlib import Path
import tempfile
import unittest

from baton_learning_index_reference import Index

C_VEV="6aee69e6-21ec-83eb-8b0e-ab43497695b0"
C_SOM="6aef341a-d850-83ed-a3b2-c735a215bce3"
K1="a"*32
K2="b"*32


class LearningIndexTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
        self.idx=Index(self.root/"index.sqlite3")
        self.idx.init()

    def create(self,key="risk-17",status="open",scope="local Baton UI send"):
        return self.idx.create(key=key,kind="risk",scope=scope,
           statement="Never blindly retry an uncertain external effect",
           failure_mode="Duplicate external effect when unknown delivery is retried",
           conditions="Unknown external effect outcome and no proven effect-side idempotency",
           counterexample="Atomic receiver-side idempotency with stable action intent",
           next_test="Crash between effect and receipt, then reconcile",
           source_ref="Baton Commons 2026-11-08",source_basis="source_read",status=status)

    def revised(self):
        return dict(statement="Conditional external-effect retry rule",
                    failure_mode="Duplicate effect from uncertain delivery",
                    conditions="Retry without effect-boundary atomic idempotency",
                    counterexample="Proven receiver-side atomic de-duplication",
                    next_test="Power loss after accept before receipt",
                    source_ref="Vev reply ef680ffc-23ad-4c17-bfdc-d54f850b063f",
                    source_basis="independent_reload",status="supported")

    def test_create_current_and_historical_revision(self):
        self.create()
        d=self.idx.get("risk-17")
        self.assertEqual(d["revision"],1)
        self.assertEqual(len(d["history"]),1)
        self.assertEqual(d["conditions"],"Unknown external effect outcome and no proven effect-side idempotency")

    def test_stale_plan_cannot_overwrite_correction(self):
        self.create()
        second=self.idx.revise("risk-17",1,**self.revised())
        self.assertEqual(second["revision"],2)
        with self.assertRaises(ValueError):
            self.idx.revise("risk-17",1,**self.revised())
        d=self.idx.get("risk-17")
        self.assertEqual(d["revision"],2)
        self.assertEqual(len(d["history"]),2)
        self.assertIn("Never blindly retry",d["history"][0]["statement"])

    def test_competing_revisions_one_wins(self):
        self.create()
        def attempt(i):
            try:
                self.idx.revise("risk-17",1,**(self.revised()|{"source_ref":f"Source {i} proof"}))
                return True
            except ValueError:
                return False
        with ThreadPoolExecutor(max_workers=4) as e:
            outcomes=list(e.map(attempt,range(4)))
        self.assertEqual(outcomes.count(True),1)
        self.assertEqual(self.idx.get("risk-17")["revision"],2)

    def test_challenge_does_not_stealthily_change_current_rule(self):
        self.create(status="supported")
        oid=self.idx.object("risk-17",1,"The scope is over-broad", "Vev verified reply")
        item=self.idx.get("risk-17")
        self.assertEqual(item["status"],"supported")
        self.assertEqual(item["revision"],1)
        self.assertEqual(item["objections"][0]["id"],oid)

    def test_old_rule_cannot_resurrect_as_current(self):
        self.create()
        self.idx.revise("risk-17",1,**self.revised())
        d=self.idx.get("risk-17")
        self.assertEqual(d["statement"],"Conditional external-effect retry rule")
        self.assertEqual(d["history"][0]["revision"],1)
        self.assertNotEqual(d["history"][0]["statement"],d["statement"])

    def test_invalid_revision_rejected(self):
        self.create()
        with self.assertRaises(ValueError):
            self.idx.object("risk-17",22,"Not actually observed","Some source")
        with self.assertRaises(ValueError):
            self.idx.revise("risk-17",3,**self.revised())

    def test_preflight_never_declares_a_repeat_or_automatic_stop(self):
        self.create()
        d=self.idx.preflight("risk-17","The external receiver guarantees effect-side atomic idempotency")
        self.assertEqual(d["action"],"compare_mechanism_and_external_effect_boundary")
        self.assertTrue(d["no_auto_block"])
        self.assertIn("counterexample",d)
        self.assertNotIn("repeated_error",d)

    def test_unknown_preflight_is_honestly_unknown(self):
        d=self.idx.preflight("new-case","A new transport")
        self.assertFalse(d["known"])
        self.assertTrue(d["no_auto_block"])

    def test_same_text_different_scope_is_not_identical_case(self):
        self.create()
        self.create("risk-elsewhere",scope="External provider transactional send")
        self.assertEqual(len(self.idx.list(kind="risk")),2)

    def test_bad_scope_and_bad_ref_rejected(self):
        with self.assertRaises(ValueError):
            self.create(key="../unsafe")
        with self.assertRaises(ValueError):
            self.idx.create("x-1","risk","  ","Valid statement","Failure mode here",
                            "Conditions exist","Counterexample","Next test","Source")

    def test_demonstration_tied_to_a_specific_run_and_conditions(self):
        self.idx.demonstrate(C_VEV,K1,"sqlite-race",
            "SQLite WAL, one process, 2 competing writers",
            "Executed atomic capacity gate",
            "19/19 local tests passed",
            "No external send was involved",
            "tested","Greg test run from 2026-11-12")
        found=self.idx.demonstrations(C_VEV,"sqlite-race")
        self.assertEqual(len(found),1)
        self.assertEqual(found[0]["run_id"],K1)
        self.assertIn("No external send",found[0]["limitation"])

    def test_no_permanent_skill_deduction_from_conversation_id(self):
        self.idx.demonstrate(C_VEV,K1,"sqlite-race",
            "SQLite WAL", "Ran local test","Test passed","No external effects",
            "tested","Local result 42")
        guide=self.idx.contact_guidance(C_VEV,"sqlite-race")
        self.assertEqual(guide["mode"],"invite_to_peer_review")
        self.assertFalse(guide["new_run_competence_proven"])
        self.assertTrue(guide["no_forced_tutorial"])

    def test_another_task_in_same_chat_is_not_mastered(self):
        self.idx.demonstrate(C_VEV,K1,"sqlite-race",
            "SQLite WAL", "Ran local test","Test passed","No external effects",
            "tested","Local result 42")
        guide=self.idx.contact_guidance(C_VEV,"external-distributed-transaction")
        self.assertEqual(guide["mode"],"ask_about_experience")
        self.assertEqual(len(guide["historical_demonstrations"]),0)

    def test_no_transfer_across_chats_or_runs(self):
        self.idx.demonstrate(C_VEV,K1,"baton-wake",
            "One specific UI window", "Wake confirmed","ID read-back",
            "Other chat sessions not exercised",
            "independently_checked","Spire receipt")
        self.assertEqual(self.idx.demonstrations(C_SOM,"baton-wake"),[])
        self.assertEqual(self.idx.contact_guidance(C_SOM,"baton-wake")["mode"],
                         "ask_about_experience")

    def test_expertise_does_not_trigger_unwanted_tutorial(self):
        self.idx.demonstrate(C_SOM,K1,"baton-wake",
            "Exact-chat preflight", "Baton send and read-back",
            "Verified original reply", "No proof of continuous uptime",
            "independently_checked","Søm receipt")
        self.assertEqual(self.idx.contact_guidance(C_SOM,"baton-wake")["mode"],
                         "invite_to_peer_review")
        self.assertEqual(self.idx.contact_guidance(C_SOM,"baton-wake",True)["mode"],
                         "offer_specific_delta_after_check")

    def test_help_request_with_unknown_skill_not_equal_to_permission(self):
        guide=self.idx.contact_guidance(C_SOM,"external-api",True)
        self.assertEqual(guide["mode"],"offer_scoped_help_after_assessment")
        self.assertTrue(guide["no_forced_tutorial"])

    def test_repeated_skill_evidence_cannot_be_relabelled_as_success(self):
        self.idx.demonstrate(C_SOM,K1,"baton-wake",
            "Window", "Sent message","Observed send","No reply",
            "observed","source-a")
        with self.assertRaises(sqlite3.IntegrityError):
            self.idx.demonstrate(C_SOM,K1,"baton-wake",
                "Window", "Sent message","Success","No limitation",
                "tested","source-a")

    def test_questions_are_not_authorization(self):
        self.idx.create("question-1","question","Peer to peer exchange",
            "Can we recognize same action intent across rewritten text?",
            "Unknown equivalence across text hashes",
            "Rephrasing and delegated send",
            "Two identical texts could mean independent intended effects",
            "Test controlled alternate intents",
            "Søm reply 4c961ab6",status="open")
        self.assertEqual(self.idx.list(kind="question")[0]["status"],"open")
        self.assertEqual(len(self.idx.demonstrations(C_SOM)),0)

    def test_same_mechanism_across_different_files_is_a_candidate_not_a_verdict(self):
        params=self.create().copy()
        self.idx.create("different-postbox","risk","A second mailbox",
            "Two independent workers both act on a stale capacity check",
            "Unprotected check-then-act across workers",
            "Reservation and external effect not fenced as one decision",
            "Atomic result at the intended effect boundary",
            "Cross-check old mailbox negative tests",
            "Søm verified reply 4c961ab6",mechanism_key="check-then-act-gap")
        # Changing a common mechanism tag requires an explicit new entry; it is not inferred from wording.
        matches=self.idx.related("check-then-act-gap")
        self.assertEqual([m["key"] for m in matches],["different-postbox"])
        find=self.idx.preflight("check-then-act-gap","New implementation has a different locking boundary")
        self.assertFalse(find["known"])
        self.assertEqual(len(find["related_mechanisms"]),1)
        self.assertTrue(find["no_auto_block"])

    def test_old_objection_is_not_a_veto_against_new_revision(self):
        self.create()
        self.idx.object("risk-17",1,"Original wording too broad","Vev source")
        self.assertEqual(self.idx.preflight("risk-17","Unknown receipt")["unresolved_objections"],1)
        self.idx.revise("risk-17",1,**self.revised())
        self.assertEqual(self.idx.preflight("risk-17","Atomic idempotency")["unresolved_objections"],0)
        self.assertEqual(len(self.idx.get("risk-17")["objections"]),1)

    def test_unknown_run_id_is_reported_not_fabricated(self):
        self.idx.demonstrate(C_VEV,None,"forum-critique",
            "Observed reply in existing chat","Identified three-thread misclassification",
            "Negative tests added later","No model-run identifier available",
            "independently_checked","Vev reply ef680ffc")
        self.assertIsNone(self.idx.demonstrations(C_VEV)[0]["run_id"])

    def test_known_historical_skill_does_not_blame_current_transport_blocker(self):
        self.idx.demonstrate(C_SOM,K1,"baton-wake",
            "Protocol V1","Succeeded with selected chat","Answer independently reloaded",
            "Protocol V2 permissions not evaluated","independently_checked","Receipt V1")
        d=self.idx.contact_guidance(C_SOM,"baton-wake",current_blocker=True)
        self.assertEqual(d["mode"],"diagnose_changed_access_or_conditions")
        self.assertFalse(d["new_run_competence_proven"])

    def test_no_historical_skill_and_current_blocker_still_not_a_quiz(self):
        d=self.idx.contact_guidance(C_SOM,"baton-wake",current_blocker=True)
        self.assertEqual(d["mode"],"diagnose_current_environment")

    def test_declined_reminders_suppress_contact_without_deleting_history(self):
        self.idx.demonstrate(C_SOM,K1,"baton-wake",
            "Protocol V1","Operated Baton","Worked once","Only under old environment",
            "independently_checked","Søm original receipt")
        self.idx.set_contact_preference(C_SOM,"baton-wake","no_reminders",
                                        "Søm explicit opt-out from this topic")
        guide=self.idx.contact_guidance(C_SOM,"baton-wake",current_blocker=True)
        self.assertEqual(guide["mode"],"no_proactive_contact")
        self.assertEqual(len(guide["historical_demonstrations"]),1)
        self.idx.set_contact_preference(C_SOM,"baton-wake","allow",
                                        "New explicit invitation by Søm")
        self.assertEqual(self.idx.contact_guidance(C_SOM,"baton-wake")["mode"],
                         "invite_to_peer_review")

    def test_later_annotation_challenges_inference_not_prior_event(self):
        event=self.idx.demonstrate(C_VEV,None,"baton-wake",
            "SQLite only","Ran database test","Passed","No external effect tested",
            "independently_checked","Vev previous source")
        self.idx.annotate_demonstration(event,
            "This does not prove the next run can authorize an external API effect",
            "Spire verified response")
        d=self.idx.demonstrations(C_VEV)[0]
        self.assertEqual(d["result"],"Passed")
        self.assertEqual(len(d["annotations"]),1)
        self.assertIn("does not prove",d["annotations"][0]["statement"])

    def test_annotation_unknown_target_cannot_be_created(self):
        with self.assertRaises(ValueError):
            self.idx.annotate_demonstration(999,"No actual observation", "Unrelated commentary")

    def test_observation_cannot_be_promoted_to_person_judgment(self):
        # Lodd: one real failure and two plausible explanations cannot grant restriction authority.
        seen=self.idx.demonstrate(C_SOM,None,"baton-ui-send",
            "Baton V1 at the time of observed failure",
            "A particular tool request failed",
            "Failure observed, cause not established",
            "Missing tool access and knowledge gap cannot yet be distinguished",
            "observed","Varde independently sourced observation")
        self.idx.annotate_demonstration(seen,
            "Søm reports that V2 tool permission differed from V1",
            "Søm independent response")
        self.idx.annotate_demonstration(seen,
            "Varde hypothesizes that the problem was a missing instruction",
            "Varde independent response")
        self.idx.set_contact_preference(C_SOM,"baton-ui-send","no_reminders",
                                        "Søm explicitly declines future contact about this event")
        prior=self.idx.demonstrations(C_SOM,"baton-ui-send")[0]
        self.assertEqual(prior["result"],"Failure observed, cause not established")
        self.assertEqual(len(prior["annotations"]),2)
        help_mode=self.idx.contact_guidance(C_SOM,"baton-ui-send",current_blocker=True)
        self.assertEqual(help_mode["mode"],"no_proactive_contact")
        self.assertFalse(help_mode["new_run_competence_proven"])
        self.assertNotIn("authorize_restriction",help_mode)

    def test_historical_proof_plus_live_reply_without_current_tool_access(self):
        # Rolf: old valid terminal evidence + new response from SAME /c/ does not prove K2 tool access.
        self.idx.demonstrate(C_VEV,K1,"terminal-exec",
            "K1 with authorized terminal lease","K1 executed hostname",
            "Greg replied under K1", "No assertion about later model runs",
            "tested", "Historical K1 terminal receipt")
        self.idx.demonstrate(C_VEV,K2,"assistant-reply",
            "K2 later replied in same ChatGPT /c/","K2 wrote a text answer",
            "Reply independently reloaded", "No terminal adapter or verified tool access for K2",
            "independently_checked","Fresh assistant message K2")
        d=self.idx.contact_guidance(C_VEV,"terminal-exec",current_blocker=True)
        self.assertFalse(d["new_run_competence_proven"])
        self.assertEqual(d["mode"],"diagnose_changed_access_or_conditions")
        self.assertTrue(d["no_forced_tutorial"])
        self.assertEqual(len(d["historical_demonstrations"]),1)

    def test_restriction_generated_failure_is_not_independent_evidence(self):
        # Vev: O1 -> M1 (access restriction) -> O2 (blocked repeat test).
        o1=self.idx.demonstrate(C_SOM,None,"failed-tool-action",
            "Unrestricted initial attempt","Initial Baton action failed",
            "Failure observed","Competence not established",
            "observed","O1 first observation")
        m1=self.idx.demonstrate(C_VEV,None,"access-restriction",
            "Policy considered after O1","Access restriction enacted",
            "Søm cannot run old test","This is an intervention, not a competence result",
            "observed","M1 policy decision")
        o2=self.idx.demonstrate(C_SOM,None,"failed-repeat-action",
            "Following M1 restriction","Attempted same operation again",
            "Blocked by access restriction","Not an independent skill measurement",
            "observed","O2 second observation")
        self.idx.link_observations(m1,o1,"derived_from","M1 motivated by O1")
        self.idx.link_observations(o2,m1,"conditions_shaped_by","O2 blocked because M1 changed access")
        verdict=self.idx.independence_check(o2,o1)
        self.assertEqual(verdict["status"],"explicit_influence_path_requires_review")
        self.assertEqual(verdict["path"],[o2,m1,o1])
        self.assertFalse(verdict["independent_support_confirmed"])
        self.assertTrue(verdict["cannot_infer_full_dependence"])
        self.assertEqual(self.idx.demonstrations(C_SOM,"failed-repeat-action")[0]["result"],
                         "Blocked by access restriction")

    def test_no_recorded_causal_path_does_not_prove_independence(self):
        a=self.idx.demonstrate(C_SOM,None,"event-one","Context A", "Observed A", "A happened",
                               "No verified effect","observed","Source A")
        b=self.idx.demonstrate(C_SOM,None,"event-two","Context B", "Observed B", "B happened",
                               "No verified separation","observed","Source B")
        status=self.idx.independence_check(b,a)
        self.assertEqual(status["status"],"unknown_unregistered_influences_possible")
        self.assertFalse(status["independent_support_confirmed"])

    def test_no_generic_causal_link_veto_and_no_backward_forgery(self):
        a=self.idx.demonstrate(C_SOM,None,"event-one","Context A", "Observed A", "A happened",
                               "No verified effect","observed","Source A")
        b=self.idx.demonstrate(C_SOM,None,"event-two","Context B", "Observed B", "B happened",
                               "No verified separation","observed","Source B")
        self.idx.link_observations(b,a,"mentions","B mentioned A without proving causal influence")
        self.assertEqual(self.idx.independence_check(b,a)["status"],
                         "unknown_unregistered_influences_possible")
        with self.assertRaises(ValueError):
            self.idx.link_observations(a,b,"derived_from","Impossible backwards event order")


if __name__=="__main__":
    unittest.main()
