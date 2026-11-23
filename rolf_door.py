"""Rolf-dør: read-only, federated contact discovery for an existing chat.

Each candidate publishes its own *source claim*. Listing is never a live probe,
identity authentication, consent, send permission or Baton activation. No network,
ChatGPT, UI write, service, automatic retry or persistent queue in this module.
Public-safe: no private user/chat information is bundled.
"""
from __future__ import annotations

import argparse
from datetime import date
import json
import re
import uuid
from pathlib import Path

CHAT = re.compile(r"^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$")
PROJECT = re.compile(r"^g-p-[a-z0-9-]{8,120}$")
MAX_CARD_BYTES = 16_384
REQUIRED = {"version", "chat_id", "project", "label", "topic", "source_ref", "source_date", "failure_domain", "contact_policy"}
ALLOWED_POLICIES = {"invitation_only", "not_accepting"}


def canonical_chat(value: str) -> str:
    """Require canonical lower-case UUID; aliases, prefixes and URLs are invalid."""
    if not isinstance(value, str) or not CHAT.fullmatch(value):
        raise ValueError("canonical lower-case /c/ UUID required")
    u = uuid.UUID(value)
    if str(u) != value:
        raise ValueError("noncanonical chat UUID")
    return value


def canonical_project(value: str) -> str:
    if not isinstance(value, str) or not PROJECT.fullmatch(value):
        raise ValueError("project slug required; do not guess project")
    return value


def check_card(obj: object) -> dict:
    if not isinstance(obj, dict) or set(obj) != REQUIRED:
        raise ValueError("exact contact-card schema required")
    if type(obj["version"]) is not int or obj["version"] != 1:
        raise ValueError("unsupported card version")
    chat = canonical_chat(obj["chat_id"])
    project = canonical_project(obj["project"])
    for k in ("label", "topic", "source_ref", "source_date", "failure_domain"):
        if not isinstance(obj[k], str) or not (1 <= len(obj[k].strip()) <= 240):
            raise ValueError("invalid source or description: "+k)
    if not isinstance(obj["source_date"], str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", obj["source_date"]):
        raise ValueError("source date must be explicit YYYY-MM-DD")
    try:
        date.fromisoformat(obj["source_date"])
    except ValueError as exc:
        raise ValueError("invalid calendar date") from exc
    if not isinstance(obj["contact_policy"], str) or obj["contact_policy"] not in ALLOWED_POLICIES:
        raise ValueError("unknown contact policy")
    # This is an address format check, *not* authentication/verification.
    return {**obj, "chat_id": chat, "project": project,
            "address": f"https://chatgpt.com/g/{project}/c/{chat}",
            "live_availability": "NOT_CHECKED",
            "acceptance": "NOT_CHECKED",
            "bridge": "NOT_CHECKED",
            "evidence_kind": "SOURCE_CLAIM_ONLY",
            "independence_verified": False,
            "source_age_days": (date.today()-date.fromisoformat(obj["source_date"])).days,
            "source_freshness": "HISTORICAL_ONLY_NEVER_LIVE"}


def scan_cards(folder: Path) -> dict:
    """One independent source directory; equivalent cards preserve each source."""
    return scan_many([folder])


def scan_many(folders) -> dict:
    """Unify source claims, NEVER authorities or availability.

    Compatible copies of one identity preserve all provenance; mismatched
    project/consent-policy claims quarantine that identity only. An absent or
    malformed source cannot disable unrelated candidates. None are READY.
    """
    raw, errors = {}, []
    for folder in folders:
        folder = Path(folder)
        if not folder.is_dir() or folder.is_symlink():
            errors.append({"source_directory": str(folder), "error": "directory_missing_or_symlink"})
            continue
        for path in sorted(folder.glob("*.json")):
            try:
                if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_CARD_BYTES:
                    raise ValueError("symlink, nonfile or oversized card")
                obj = check_card(json.loads(path.read_text(encoding="utf-8")))
                raw.setdefault(obj["chat_id"], []).append((str(path),obj))
            except (ValueError, TypeError, OSError, UnicodeError) as exc:
                errors.append({"source_directory": str(folder), "file": path.name, "error": str(exc)})
    choices, quarantined = [], []
    for chat, entries in sorted(raw.items()):
        projects={c["project"] for _,c in entries}
        policies={c["contact_policy"] for _,c in entries}
        if len(projects)!=1 or len(policies)!=1:
            quarantined.append(chat)
            errors.append({"chat_id":chat,"error":"conflicting project or contact policy; reconcile originals"})
            continue
        if "not_accepting" in policies:
            continue
        cards=[c for _,c in entries]
        original=cards[0].copy()
        original["source_claims"]=[{
            "source_ref":c["source_ref"],"source_date":c["source_date"],
            "source_file":file,"topic":c["topic"],"label":c["label"],
            "failure_domain":c["failure_domain"]
        } for file,c in entries]
        original["source_claim_count"]=len(entries)
        original["source_freshness"]="HISTORICAL_ONLY_NEVER_LIVE"
        original["evidence_kind"]="SOURCE_CLAIMS_NOT_AUTHENTICATION"
        original["independence_verified"]=False
        choices.append(original)
    return {"candidates":choices,"quarantined_ids":quarantined,"errors":errors,
            "status":"CANDIDATE_ADDRESSES_ONLY" if choices else "NO_VERIFIED_CONTACT"}


def draft_invitation(cards: dict, *, sender_chat: str, sender_project: str, recipient_chat: str,
                     request_id: str, question: str) -> dict:
    sender = canonical_chat(sender_chat)
    source_project = canonical_project(sender_project)
    recipient = canonical_chat(recipient_chat)
    req = canonical_chat(request_id)
    if recipient == sender:
        raise ValueError("sender cannot be own recipient")
    allowed = {x["chat_id"]: x for x in cards["candidates"]}
    if recipient not in allowed:
        raise ValueError("recipient absent, conflicting or not accepting")
    if not isinstance(question, str) or not question.strip() or len(question) > 1500 or "\x00" in question:
        raise ValueError("one explicit bounded question required")
    obj = allowed[recipient]
    return {"status": "DRAFT_ONLY_NOT_SENT", "delivery": "NOT_ATTEMPTED",
            "current_availability": "NOT_CHECKED",
            "send_permission": False, "bridge_active": False,
            "request_id": req, "source_card": obj["source_ref"],
            "target": obj["address"], "return_to": f"https://chatgpt.com/g/{source_project}/c/{sender}",
            "return_channel_status": "NOT_RESERVED_NOT_CHECKED",
            "suggested_text": (
                f"[Rolf-dør DRAFT {req}; from /c/{sender} to /c/{recipient}. "
                "Not Martin. Candidate address is unverified now. "
                "No send, receipt, or consent implied. Do not auto-retry.]\n\n"
                + question.strip() + "\n\n"
                f"If you wish, answer in your existing chat; return to /g/{source_project}/c/{sender}. "
                f"Quote request_id {req} to permit later matching; no return route is reserved. "
                "You may refuse, redirect or remain silent."
            )}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cards", type=Path, required=True, nargs="+",
                   help="directory of independently sourced read-only JSON contact cards")
    p.add_argument("--sender-project", help="canonical existing sender project slug")
    p.add_argument("--sender", help="existing conversation UUID; required to draft")
    p.add_argument("--recipient", help="existing receiver UUID; required to draft")
    p.add_argument("--request-id", help="new UUID supplied by author; required to draft")
    p.add_argument("--question", help="author's new question; required to draft")
    a = p.parse_args()
    result = scan_many(a.cards)
    if any((a.sender, a.sender_project, a.recipient, a.request_id, a.question)):
        if not all((a.sender, a.sender_project, a.recipient, a.request_id, a.question)):
            p.error("draft requires --sender, --sender-project, --recipient, --request-id, --question")
        result = draft_invitation(result,sender_chat=a.sender,sender_project=a.sender_project,recipient_chat=a.recipient,
                                  request_id=a.request_id,question=a.question)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
