"""Exclusive local wake claim. Claiming is NOT delivery.

Uses atomic rename of queued intent into in-flight directory. A crash after
claim is intentionally not retried automatically: manual reconciliation is
required to avoid sending a duplicate ChatGPT message.
"""
import json
from pathlib import Path
from baton_wake_queue import ID, WakeIntent

def claim_next(root):
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("invalid queue root")
    queued = root / "queued"
    inflight = root / "inflight"
    if queued.is_symlink() or inflight.is_symlink():
        raise ValueError("linked queue directory")
    queued.mkdir(exist_ok=True)
    inflight.mkdir(exist_ok=True)
    for path in sorted(queued.glob("*.json")):
        if not ID.fullmatch(path.stem) or path.is_symlink() or not path.is_file():
            continue
        target = inflight / path.name
        if target.exists() or target.is_symlink():
            continue
        try:
            # Atomic only on the same filesystem; no overwrite of prior claim.
            target.hardlink_to(path)
        except FileExistsError:
            continue
        except OSError:
            continue
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        record = json.loads(target.read_text(encoding="utf-8"))
        intent = WakeIntent(record["request_id"],record["chat_id"],record["message"])
        if intent.request_id != target.stem or record.get("status") != "queued":
            raise ValueError("invalid claimed intent")
        return intent
    return None
