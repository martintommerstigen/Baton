"""In-memory browser integration test: real ChatGPTUIDriver + ledger + chain.

This exercises the production DOM adapter without a browser/network. It cannot
verify selectors on ChatGPT's live interface.
"""
import tempfile
import unittest
from chatgpt_ui_driver import ChatGPTUIDriver
from wake_contract import WakeLedger
from wake_chain import ChainPlan, run_chain

A="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
B="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
C="cccccccc-cccc-cccc-cccc-cccccccccccc"

class Turn:
    def __init__(self,role,text,mid=None):
        self.role,self.text,self.mid=role,text,mid
    def get_attribute(self,name):
        return {"data-message-author-role":self.role,"data-message-id":self.mid}.get(name)
    def inner_text(self): return self.text

class Locator:
    def __init__(self,nodes): self.nodes=nodes
    def count(self): return len(self.nodes)
    def nth(self,i): return self.nodes[i]
    def filter(self,has_text):
        return Locator([n for n in self.nodes if has_text in n.inner_text()])

class Composer:
    def __init__(self): self.text=""
    def count(self): return 1
    def is_visible(self): return True
    def inner_text(self): return self.text
    def fill(self,text): self.text=text

class Send:
    def __init__(self,page): self.page=page
    def count(self): return 1
    def is_enabled(self): return bool(self.page.composer.text)
    def click(self):
        text=self.page.composer.text
        self.page.turns.append(Turn("user",text))
        if self.page.chat==B:
            response="BATON_NEXT "+C
        else:
            response="Received in C"
        self.page.turns.append(Turn("assistant",response,"turn-"+self.page.chat[-4:]))
        self.page.composer.text=""
        self.page.send_count+=1

class Page:
    def __init__(self,chat):
        self.chat=chat
        self.url="https://chatgpt.com/c/"+chat
        self.composer=Composer()
        self.send=Send(self)
        self.turns=[]
        self.send_count=0
    def locator(self,selector):
        if selector=="#prompt-textarea": return self.composer
        if selector=='[data-testid="send-button"]': return self.send
        if selector=='[data-testid="stop-button"]': return Locator([])
        if selector=="[data-message-author-role]": return Locator(self.turns)
        if selector=='[data-message-author-role="user"]':
            return Locator([t for t in self.turns if t.role=="user"])
        if selector=='[data-message-author-role="assistant"]':
            return Locator([t for t in self.turns if t.role=="assistant"])
        raise AssertionError(selector)

class BrowserIntegrationTests(unittest.TestCase):
    def test_two_real_dom_drivers(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger=WakeLedger(tmp+"/db")
            pb,pc=Page(B),Page(C)
            db=ChatGPTUIDriver(pb,frozenset({B}))
            dc=ChatGPTUIDriver(pc,frozenset({C}))
            plan=ChainPlan(A,B,C,"msg1","msg2","ask B","ask C","d1","d2")
            result=run_chain(ledger,db,dc,plan,db.read_assistant_turn)
            self.assertEqual(result,{"a_to_b":"verified","b_to_c":"verified"})
            self.assertEqual((pb.send_count,pc.send_count),(1,1))
            again=run_chain(ledger,db,dc,plan,db.read_assistant_turn)
            self.assertEqual(again,result)
            self.assertEqual((pb.send_count,pc.send_count),(1,1))
            self.assertEqual(ledger.provenance("msg2")[2],"turn-"+B[-4:])

if __name__=="__main__": unittest.main()
