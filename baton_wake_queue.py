"""Headless Baton wake queue: lightweight, deterministic, no Qt or browser imports.

Queue records are *intent*, not proof of ChatGPT delivery. The optional
ChatGPT adapter must verify the exact target and record delivery separately.
"""
from dataclasses import dataclass
import json
import re
from pathlib import Path

ID = re.compile(r"^[0-9a-f]{32}$")
CHAT = re.compile(r"^[0-9a-f]{8}-[0-9a-f-]{20,64}$", re.I)
MAX_MESSAGE = 4000

@dataclass(frozen=True)
class WakeIntent:
    request_id: str
    chat_id: str
    message: str

    def __post_init__(self):
        if not isinstance(self.request_id, str) or not ID.fullmatch(self.request_id):
            raise ValueError("invalid request ID")
        if not isinstance(self.chat_id, str) or not CHAT.fullmatch(self.chat_id):
            raise ValueError("invalid target conversation")
        if not isinstance(self.message, str) or not 1 <= len(self.message) <= MAX_MESSAGE:
            raise ValueError("invalid message")

    def to_record(self):
        return {"request_id": self.request_id, "chat_id": self.chat_id,
                "message": self.message, "status": "queued"}

def enqueue(directory, intent):
    """Atomic create-only intent; never overwrite or resend existing request."""
    if not isinstance(intent, WakeIntent):
        raise TypeError("WakeIntent required")
    root = Path(directory)
    if root.is_symlink():
        raise ValueError("symlinked queue denied")
    root.mkdir(parents=True, exist_ok=True)
    destination = root / (intent.request_id + ".json")
    payload = json.dumps(intent.to_record(), sort_keys=True).encode("utf-8")
    try:
        with destination.open("xb") as f:
            f.write(payload)
    except FileExistsError:
        raise ValueError("duplicate request ID") from None
    return destination
