"""Baton wake receipts: a transport ACK is not proof a ChatGPT chat woke.

Only a reply generated in the intended conversation, quoting the challenge and
request ID, can be treated as evidence of a completed wake. This module does
not send a wake or access ChatGPT; it validates the receipt envelope.
"""
import re

NONCE = re.compile(r"^[0-9a-f]{32}$")
CHAT = re.compile(r"^/c/[0-9a-f-]{20,80}$")
STATES = frozenset({"queued", "delivered", "opened", "responded", "failed"})

def validate_wake_receipt(request, receipt):
    if not isinstance(request, dict) or not isinstance(receipt, dict):
        return False
    if set(request) != {"id", "target_chat", "challenge"}:
        return False
    if set(receipt) != {"id", "target_chat", "challenge", "state", "message_id"}:
        return False
    if not isinstance(request["id"], str) or not NONCE.fullmatch(request["id"]):
        return False
    if not isinstance(request["target_chat"], str) or not CHAT.fullmatch(request["target_chat"]):
        return False
    if not isinstance(request["challenge"], str) or not NONCE.fullmatch(request["challenge"]):
        return False
    if any(receipt[k] != request[k] for k in ("id", "target_chat", "challenge")):
        return False
    if receipt["state"] not in STATES:
        return False
    if receipt["state"] == "responded":
        return isinstance(receipt["message_id"], str) and bool(receipt["message_id"].strip())
    return receipt["message_id"] is None

def is_confirmed_wake(request, receipt):
    """Structural check only; provenance/authenticity must be verified separately."""
    return validate_wake_receipt(request, receipt) and receipt["state"] == "responded"
