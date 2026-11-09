"""Bounded, allowlisted A→B→C wake-chain orchestrator.

B must explicitly request the preauthorized C target in its assistant response.
The controller, not a claimed independent ChatGPT API, performs the UI action.
Only the predetermined harmless challenge is sent to C.
"""
from dataclasses import dataclass
from wake_adapter import wake_once

@dataclass(frozen=True)
class ChainPlan:
    a: str
    b: str
    c: str
    first_id: str
    second_id: str
    first_body: str
    second_body: str
    first_digest: str
    second_digest: str

def next_target_from_reply(reply_text, expected_target):
    # Exact one-line control statement; reject prose, multiple commands and
    # other targets. Treat model output as an untrusted request, not authority.
    expected=f'BATON_NEXT {expected_target}'
    lines=[line.strip() for line in reply_text.splitlines() if line.strip()]
    commands=[line for line in lines if line.startswith('BATON_NEXT')]
    if commands != [expected]:
        return None
    return expected_target

def run_chain(ledger, driver_b, driver_c, plan, read_reply):
    if len({plan.a,plan.b,plan.c})!=3 or plan.first_id==plan.second_id:
        raise ValueError('Distinct conversation and message IDs required')
    first=wake_once(ledger,driver_b,plan.first_id,plan.a,plan.b,
                    plan.first_digest,plan.first_body)
    if first!='verified':
        return {'a_to_b':first,'b_to_c':'not_attempted'}
    turn_id=ledger.state(plan.first_id)[2]
    reply=read_reply(plan.b,turn_id)
    if not isinstance(reply,str) or next_target_from_reply(reply,plan.c) is None:
        return {'a_to_b':'verified','b_to_c':'not_authorized'}
    second=wake_once(ledger,driver_c,plan.second_id,plan.b,plan.c,
                     plan.second_digest,plan.second_body)
    return {'a_to_b':'verified','b_to_c':second}
