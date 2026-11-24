"""Small append-only Baton UI observation log.

Records only request IDs, target chat IDs and state transitions, never bodies,
tokens or ChatGPT cookies. UI observation is not proof of persistent delivery.
"""
import json
import os
from pathlib import Path
import re
import time

ID=re.compile(r"^[0-9a-f]{32}$")
STATUS=frozenset({"click_attempted","composer_failed","send_not_ready","user_visible_ui","assistant_reply_visible_ui","ui_observation_timeout","target_changed"})

def log_event(request_id, target_chat, status, *, root=None, assistant_message_id=None):
    if not isinstance(request_id,str) or not ID.fullmatch(request_id):
        raise ValueError("invalid request ID")
    if not isinstance(target_chat,str) or not re.fullmatch(r"[0-9a-f-]{20,80}",target_chat,re.I):
        raise ValueError("invalid target chat")
    if status not in STATUS:
        raise ValueError("invalid status")
    base=Path(root) if root is not None else Path.home()/".local/share/baton/ui-events"
    if base.is_symlink():
        raise ValueError("symlinked event folder")
    base.mkdir(parents=True,exist_ok=True,mode=0o700)
    entry={"request_id":request_id,"target_chat":target_chat,"status":status,
           "observed_at_unix":time.time(),"assistant_message_id":assistant_message_id}
    destination=base/(request_id+"."+status+".json")
    fd=os.open(destination,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,"w",encoding="utf-8") as file:
        json.dump(entry,file,sort_keys=True)
        file.write("\n")
    return destination
