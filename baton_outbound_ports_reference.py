"""Baton external effect boundary (experimental, not wired to live sender).

Only the Ruben *Baton transport queue* has an existing authenticated client.
Queue acceptance is NOT a model reply. Messenger personal chats have no
general-purpose official API; Page messaging requires an approved business
connection and a verified policy window. No tool, proposal, or topic creates
its own grant, and no environment credentials are loaded here.
"""
from dataclasses import dataclass
import hashlib
import json
import re
from baton_action_authority_reference import ActionFence
from baton_multiroom_reference import CHANNELS

ATOM = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,127}$")


def _atom(x):
    if not isinstance(x, str) or not ATOM.fullmatch(x):
        raise ValueError("invalid stable id")
    return x


@dataclass(frozen=True)
class ExternalMessage:
    action_id: str
    channel: str
    account: str
    recipient: str
    text: str

    def validate(self):
        _atom(self.action_id)
        if self.channel not in CHANNELS or CHANNELS[self.channel]["kind"]!="external":
            raise ValueError("not an external channel")
        _atom(self.account)
        _atom(self.recipient)
        if not isinstance(self.text,str) or not 1<=len(self.text.strip())<=3500:
            raise ValueError("invalid text")
        return self

    @property
    def effect_key(self):
        """Exact channel + account + recipient + content, all covered."""
        self.validate()
        canonical=json.dumps({
            "channel":self.channel,"account":self.account,
            "recipient":self.recipient,"text":self.text
        },sort_keys=True,ensure_ascii=False,separators=(",",":"))
        return "baton-effect-"+hashlib.sha256(canonical.encode()).hexdigest()


class ExternalPorts:
    def __init__(self,authority_fence:ActionFence):
        self.fence=authority_fence

    def draft(self,message:ExternalMessage):
        """Never sends, even if a valid account or recipient was discovered."""
        m=message.validate()
        return {"channel":m.channel,"recipient_hint":m.recipient,
                "action_id":m.action_id,"effect_key":m.effect_key,
                "state":"proposal_only","sent":False,"authorized":False}

    def prepare_ruben_queue(self, *, message, grant_id, actor, lease_token,
                            client, expected_revision=1):
        """One authorized Baton queue attempt; no auto retry, no model claim.

        The caller MUST be an authenticated Core adapter. It must separately
        verify that the recipient Baton identity belongs to Ruben and that
        Ruben has opted into the specific external contact. Passing strings
        here does NOT establish that fact. Deliberately not exposed via UI.
        """
        m=message.validate()
        if m.channel!="ruben_baton":
            raise PermissionError("this sender only implements Ruben queue transport")
        _atom(grant_id);_atom(actor);_atom(lease_token)
        if not isinstance(expected_revision,int) or isinstance(expected_revision,bool) or expected_revision<1:
            raise ValueError("invalid revision")
        if not self.fence.reserve(action_id=m.action_id,grant_id=grant_id,
               lease_token=lease_token,actor_id=actor,requested_effect_key=m.effect_key):
            return {"state":"not_authorized","sent":False}
        if not self.fence.begin_effect(action_id=m.action_id,grant_id=grant_id,
               reserved_revision=expected_revision,lease_token=lease_token,
               actor_id=actor,requested_effect_key=m.effect_key):
            return {"state":"not_authorized_at_effect","sent":False}
        # The effect is now UNKNOWN even if a crash/timeout occurs before HTTP
        # response. The fence must not become pending merely because of error.
        try:
            reply=client.send(m.recipient,m.text,message_id=m.action_id)
        except Exception:
            return {"state":"effect_unknown_no_retry","sent":None,
                    "delivery_verified":False,"model_reply_verified":False}
        status=reply.get("status") if isinstance(reply,dict) else None
        if status in ("queued","already_queued","client_acknowledged"):
            return {"state":"queue_accepted_not_delivered","queue_status":status,
                    "sent":True,"delivery_verified":False,"model_reply_verified":False}
        return {"state":"effect_unknown_no_retry","sent":None,
                "delivery_verified":False,"model_reply_verified":False}

    @staticmethod
    def messenger_private_draft(*, recipient_hint, text):
        """Use a separate user-approved messenger composer, not Meta Page API."""
        if not isinstance(recipient_hint,str) or not 2<=len(recipient_hint)<=180:
            raise ValueError("invalid contact hint")
        if not isinstance(text,str) or not 1<=len(text.strip())<=3500:
            raise ValueError("invalid draft")
        return {"channel":"messenger_personal","recipient_hint":recipient_hint,
                "draft":text,"state":"human_review_required",
                "sent":False,"delivery_verified":False}

    @staticmethod
    def messenger_page_status():
        return {"channel":"messenger_page",
                "state":"not_connected_to_meta_page_or_verified_recipient",
                "requires":["Page access token","pages_messaging permission",
                            "Page-scoped recipient ID","verified messaging window",
                            "explicit action grant"],
                "sent":False}
