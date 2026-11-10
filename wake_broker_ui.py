"""B1 experimental broker gate for an existing ChatGPT UI driver.

Offline integration seam, NOT a trusted live UI executor. The injected broker
client MUST authenticate the connected server (e.g. Ronja B5 SO_PEERCRED
client, once integrated). Never use wake_admission_broker.query as a trusted
production client: it sends bytes before checking the server's identity.

No retries. A broker response is admission state, not proof of a UI click,
assistant turn, or B->C source identity.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Callable

from chatgpt_ui_driver import ChatGPTUIDriver

_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")


class BrokerOutcomeUncertain(RuntimeError):
    """Broker state may have changed; caller must not attempt another send."""


@dataclass
class BrokerGatedUIDriver:
    """Inject a verified one-shot broker client into B1's final click boundary.

    The client is deliberately supplied by the caller; this class cannot
    authenticate a socket path, ChatGPT turn, or peer identity by itself.
    A production runner must supply a dedicated-UID verified peer client and
    independently observed source-turn evidence before invoking this driver.
    """

    driver: ChatGPTUIDriver
    broker_request: Callable[[dict], dict]
    sender_id: str
    origin_turn_id: str

    def __post_init__(self):
        if not callable(self.broker_request):
            raise TypeError("Verified broker request callback required")
        for name in ("sender_id", "origin_turn_id"):
            value = getattr(self, name)
            if type(value) is not str or not _ID.fullmatch(value):
                raise ValueError(f"Invalid {name}")

    def submit_once(self, conversation_id: str, message_id: str, body: str):
        # The existing UI driver checks allowlist, URL, draft, exact readback,
        # active generation and the pause marker before this callback runs.
        # No broker state is consumed if that preflight rejects the attempt.
        if type(body) is not str or not body.strip():
            raise ValueError("Nonempty approved body required")
        if type(conversation_id) is not str or not _ID.fullmatch(conversation_id):
            raise ValueError("Invalid target conversation")
        if type(message_id) is not str or not _ID.fullmatch(message_id):
            raise ValueError("Invalid message ID")
        envelope = {
            "conversation_id": conversation_id,
            "message_id": message_id,
            "origin_turn_id": self.origin_turn_id,
            "sender_id": self.sender_id,
            "payload_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
        }

        def before_click():
            # No network request or broker admission before exact UI preflight.
            # Every failure here is conservatively uncertain, including a
            # response that says rejected: a prior request may have committed.
            try:
                admission = self.broker_request({"op": "admit", **envelope})
                if admission != {"state": "admitted_not_delivered"}:
                    raise BrokerOutcomeUncertain("Broker admission not confirmed")
                started = self.broker_request({"op": "begin_click", **envelope})
                if started != {"state": "click_started_uncertain"}:
                    raise BrokerOutcomeUncertain("Durable click-start not confirmed")
            except Exception as exc:
                if isinstance(exc, BrokerOutcomeUncertain):
                    raise
                raise BrokerOutcomeUncertain(
                    "Broker outcome ambiguous; never retry automatically"
                ) from exc

        # Any exception after broker admission is propagated as uncertain by
        # wake_adapter.wake_once, unless the UI preflight proved no broker call
        # happened (PreSubmissionRejected).
        self.driver.submit_once(conversation_id, message_id, body,
                                before_click=before_click)

    def observe_reply(self, conversation_id, message_id, expected_digest=None):
        return self.driver.observe_reply(conversation_id, message_id,
                                         expected_digest)

    def read_assistant_turn(self, conversation_id, assistant_turn_id):
        return self.driver.read_assistant_turn(conversation_id, assistant_turn_id)

    def list_assistant_turn_ids(self, conversation_id):
        return self.driver.list_assistant_turn_ids(conversation_id)

    def is_generating(self, conversation_id):
        return self.driver.is_generating(conversation_id)
