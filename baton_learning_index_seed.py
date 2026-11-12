"""Seed a ONE-TIME nonproduction example from independently reloaded Baton replies.

Not a curriculum, not a copy of chat history, not model/identity authentication.
All claims below remain explicitly conditional. Never overwrites an existing DB.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path

from baton_learning_index_reference import Index

RECEIPTS = {
    "vev":"baton-fresh-1106dfbb5bf345e3a1bb330d75b39550.json",
    "som":"baton-fresh-eb5f53f7b2714714bd5c365d8eef7ee0.json",
    "varde":"baton-fresh-cc359e5c9b5740fdacb0d9cff6590525.json",
    "spire":"baton-fresh-d07c67ede70b4684a02cc17042e55bcd.json",
    "lodd":"baton-fresh-a4bdfb68c61446b6ae25f38e56b45c54.json",
    "rolf":"baton-fresh-026c354045e6430e900eed53ab143edb.json",
    "vev_feedback":"baton-fresh-05979b4d41154346ab4974b9d9985fa6.json",
}

def verified_source(path):
    d=json.loads(path.read_text(encoding="utf8"))
    v=d.get("independent_reload_verified",{})
    if (d.get("status")!="reply_observed_in_exact_chat"
            or not v.get("same_reply_id") or not v.get("same_reply_sha256")
            or not v.get("source_bound") or v.get("target_url")!=d.get("target_url")):
        raise ValueError("not an independently reloaded exact-chat reply")
    if hashlib.sha256(d["return_text"].encode()).hexdigest()!=d["return_sha256"]:
        raise ValueError("content digest mismatch")
    return (d["target_url"],d["return_id"],d["name"])


def main():
    os.umask(0o077)
    p=argparse.ArgumentParser()
    p.add_argument("--db",default=str(Path.home()/".local/state/baton/learning-index-reference/index.sqlite3"))
    p.add_argument("--receipts",default=str(Path.home()/".local/state/baton/continuity"))
    a=p.parse_args()
    db=Path(a.db)
    if db.exists() or db.is_symlink():raise SystemExit("Refuse to overwrite or reseed an existing example")
    source={}
    for key,filename in RECEIPTS.items():
        url,mid,name=verified_source(Path(a.receipts)/filename)
        source[key]=f"{url}#assistant={mid}"
    idx=Index(db);idx.init()

    idx.create("risk-uncertain-external-retry","risk",
        "Baton external message/side-effect send",
        "Blind resending after uncertain external effects risks duplicate effects",
        "Delivery timed out, the external effect may have happened, and sender repeats without effect-boundary atomic idempotency",
        "Uncertain external outcome; new send; no documented idempotency at the external effect boundary",
        "Recipient guarantees atomic deduplication for the same authorized intent and effect within its scope",
        "Crash after external effect and before receipt; compare exactly-once behavior",
        source["vev"],source_basis="independent_reload",status="open",
        mechanism_key="uncertain-effect-duplication")
    idx.create("risk-check-act-capacity","risk",
        "SQLite capacity gate on two concurrent producers",
        "Capacity can be exceeded when check and write are not one protected decision",
        "Two workers read 255 before each inserts one of a maximum 256",
        "Concurrent reads before guarded shared resource consumption",
        "Capacity decision protected atomically at the relevant effect boundary",
        "Repeat 255→257 negative control; then change only the resource boundary",
        source["som"],source_basis="independent_reload",status="open",
        mechanism_key="check-then-act-gap")
    idx.create("risk-check-act-mailbox","risk",
        "Baton shared message reservation with external send",
        "Same check-then-act mechanism may recur under new names and message IDs",
        "Two workers each see no unresolved contact and reserve/send independently",
        "Shared condition tested outside the protected reservation/commit boundary",
        "One authorized effect per stable intended action, with external outcome reconciliation",
        "Compare changing message IDs and worker counts while preserving intended external effect",
        source["som"],source_basis="independent_reload",status="open",
        mechanism_key="check-then-act-gap")
    idx.create("risk-rule-branch-composition","risk",
        "Proposed merger of two locally valid Baton policy revisions",
        "Combining two scoped rules can grant an unintended privilege",
        "One fork requires fresh source verification; another permits no-fresh invitation transport; a merged exception treats executable attachment as invitation",
        "Recipient automatically executes an attachment disguised as a benign invitation",
        "Text-only invitation with no privileged action and explicit trusted separation from executable content",
        "Try combining independent rule branches; prove no unapproved external execution",
        source["varde"],source_basis="independent_reload",status="open",
        mechanism_key="policy-composition-scope")
    idx.create("risk-pedagogy-tool-access","risk",
        "Teaching someone Baton after an earlier demonstrated success",
        "A past correct demonstration may become an unfair competence inference",
        "An old run succeeded on V1, but new run lacks permissions for V2",
        "Current failure is assumed to be learner ignorance rather than changed tool access",
        "Compare available operations and transport version before offering targeted help",
        "Simulate valid V1 skill, denied V2 execution, and no competence quiz",
        source["spire"],source_basis="independent_reload",status="open",
        mechanism_key="historical-demo-not-current-access")
    idx.create("question-action-intent-across-rewording","question",
        "Safe Baton cross-chat effect identity",
        "How can two reworded or delegated messages be recognized as the same intended external effect?",
        "Text hashes differ while intended side effect remains the same",
        "Distinct body or message ID is insufficient to prove distinct intent",
        "Identical text can also represent separately authorized actions",
        "Construct positive and negative same-intent examples under independent authorizations",
        source["som"],source_basis="independent_reload",status="open",
        mechanism_key="external-effect-intent")
    idx.create("question-observation-feedback","question",
        "Six Baton conversations and one shared resource",
        "How can a restriction that changes a later observation be kept from laundering that observation into independent proof?",
        "O1 failure leads to M1 access restriction; O2 failure results from the restriction",
        "Earlier decision affects the conditions that produced the next data",
        "M1 may affect O2 only partly; a genuine independent test can still carry new information",
        "Test O1→M1→O2 and a separate control with genuine new information",
        source["vev_feedback"],source_basis="independent_reload",status="open",
        mechanism_key="feedback-confounded-evidence")
    idx.create("question-epistemic-to-authority","question",
        "Peer judgments of another participant's competency",
        "How do we preserve an authentic failure and contradictory explanations without granting unjustified power to restrict a participant?",
        "Observation is promoted to general judgment about a person or alias",
        "Source observation and interpretive/operational mandate are conflated",
        "Different tool-access conditions explain the failure without a skill deficit",
        "Test a failed call plus competing explanations without automatically authorizing access restriction",
        source["lodd"],source_basis="independent_reload",status="open",
        mechanism_key="epistemic-authority-laundering")
    idx.create("question-current-run-capability","question",
        "Baton handoff and active run verification",
        "Can old genuine terminal access and a new reply in the same chat be mistaken for current model-run tool authority?",
        "A prior run executed hostname, but later reply lacks the terminal adapter",
        "Proof from different runs is combined as though it described one current execution",
        "A fresh current-run challenge bound to actual authorized tool execution",
        "Compare old proof + new reply against a true fresh adapter-bound challenge",
        source["rolf"],source_basis="independent_reload",status="open",
        mechanism_key="cross-run-proof-composition")
    # Evidence is a reloaded response, NOT proof of model-run identity or actual tool control.
    demos=[
       ("vev","reason-about-conditional-failure",
        "Prior studies of Baton cross-thread corrections",
        "Constructed counterexample to timeless error lists and permanent expertise labels",
        "Original reply independently reloaded",
        "No runtime tool execution or model-run identity demonstrated"),
       ("som","recognize-cross-context-check-act-gap",
        "Earlier negative tests on signal capacity and mailbox reservation",
        "Mapped one invariant across two resources and noted the external effect boundary",
        "Original reply independently reloaded",
        "Cross-context mechanism is proposed here, not experimentally replicated here"),
       ("varde","reason-about-policy-forks",
        "Previously investigated two signed key rotations",
        "Constructed scoped two-rule composition counterexample",
        "Original reply independently reloaded",
        "Counterexample is a thought experiment; no production policy merge tested"),
       ("spire","diagnose-education-versus-tool-access",
        "Earlier Baton success with changed transport constraints",
        "Constructed case where competence quiz misdiagnoses missing current access",
        "Original reply independently reloaded",
        "No actual V1/V2 regression run or new model-run identity established"),
       ("lodd","separate-observation-from-authority",
        "Source-bound disagreement about failure and tool access",
        "Separated event, competing explanation, and authority to restrict others",
        "Original reply independently reloaded",
        "The suggested negative test was not itself run by Lodd"),
       ("rolf","distinguish-historical-proof-from-current-access",
        "Old terminal receipt and newer assistant reply in same chat",
        "Constructed false-positive continuity witness and explicitly marked it untested",
        "Original reply independently reloaded",
        "No current-run tool challenge was executed by this peer"),
       ("vev_feedback","trace-restriction-generated-observations",
        "O1 failure, M1 restriction, O2 failure in six-peer hypothetical",
        "Identified self-generated evidential loop and proposed negative controls",
        "Original reply independently reloaded",
        "Feedback scenario is hypothetical; no live six-way stress test was run")
    ]
    for name,task,conditions,action,result,limitation in demos:
        url,mid,alias=verified_source(Path(a.receipts)/RECEIPTS[name])
        chat_id=url.split("/c/")[1]
        idx.demonstrate(chat_id,None,task,conditions,action,result,limitation,
                        "independently_checked",source[name])
    print(json.dumps({"db":str(db),"items":len(idx.list()),"risks":len(idx.list("risk")),
                      "open_questions":len(idx.list("question")),
                      "demonstrations":len(demos),
                      "no_prod_adapter":True},ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
