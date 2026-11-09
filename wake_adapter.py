"""Transport-neutral controller adapter for an existing ChatGPT conversation.

The adapter NEVER creates a new conversation and NEVER retries a potentially
submitted UI message. The caller supplies an authorized UI driver.
"""
from dataclasses import dataclass
from typing import Protocol
from wake_contract import WakeLedger

@dataclass(frozen=True)
class Observation:
    conversation_id: str
    assistant_turn_id: str

class ExistingChatDriver(Protocol):
    def submit_once(self, conversation_id: str, message_id: str, body: str) -> None: ...
    def observe_reply(self, conversation_id: str, message_id: str) -> Observation | None: ...

def wake_once(ledger: WakeLedger, driver: ExistingChatDriver,
              message_id: str, source: str, target: str, digest: str, body: str,
              source_turn_id: str | None = None) -> str:
    """One authorized attempt. A crash leaves 'submitting', never auto-retries."""
    ledger.request(message_id, source, target, digest, source_turn_id)
    if not ledger.begin_submission(message_id):
        return ledger.state(message_id)[1]
    try:
        driver.submit_once(target, message_id, body)
        observation = driver.observe_reply(target, message_id)
        if observation is None:
            ledger.mark_uncertain(message_id)
            return "uncertain"
        ledger.verify(message_id, observation.conversation_id, observation.assistant_turn_id)
        return "verified"
    except Exception:
        ledger.mark_uncertain(message_id)
        raise

def reconcile(ledger: WakeLedger, driver: ExistingChatDriver, message_id: str) -> str:
    """Read-only reconciliation; never sends another message."""
    row=ledger.state(message_id)
    if row is None: raise ValueError("unknown message")
    target,state,_=row
    if state=="verified": return state
    if state not in ("submitting","uncertain"): return state
    observation=driver.observe_reply(target,message_id)
    if observation is None: return state
    ledger.verify(message_id,observation.conversation_id,observation.assistant_turn_id)
    return "verified"
