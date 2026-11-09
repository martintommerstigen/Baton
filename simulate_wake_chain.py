"""Offline deterministic proof that the ledger + chain logic work end to end.

Does NOT claim to wake real ChatGPT chats. No Playwright or network needed.
"""
import tempfile
from wake_contract import WakeLedger
from wake_adapter import Observation
from wake_chain import ChainPlan, run_chain

class SimulatedExistingChat:
    def __init__(self, chat):
        self.chat=chat
        self.sends=[]
    def submit_once(self, chat, message_id, body):
        assert chat==self.chat
        self.sends.append((message_id,body))
    def observe_reply(self, chat, message_id):
        if any(mid==message_id for mid,_ in self.sends):
            return Observation(chat, message_id+"-assistant")
        return None

def run():
    with tempfile.TemporaryDirectory() as tmp:
        ledger=WakeLedger(tmp+"/ledger.sqlite")
        b=SimulatedExistingChat("B")
        c=SimulatedExistingChat("C")
        plan=ChainPlan("A","B","C","A-B-001","B-C-001",
                       "Please request BATON_NEXT C","Hello from B",
                       "digest1","digest2")
        result=run_chain(ledger,b,c,plan,lambda chat,turn:"BATON_NEXT C")
        assert result=={"a_to_b":"verified","b_to_c":"verified"},result
        assert len(b.sends)==1 and len(c.sends)==1
        replay=run_chain(ledger,b,c,plan,lambda chat,turn:"BATON_NEXT C")
        assert replay==result
        assert len(b.sends)==1 and len(c.sends)==1
        return {"simulation":result,"unique_sends":2,"replay_sends":0}

if __name__=="__main__":
    import json
    print(json.dumps(run(),sort_keys=True))
