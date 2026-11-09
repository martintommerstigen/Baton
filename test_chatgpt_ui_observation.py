import unittest
from chatgpt_ui_driver import ChatGPTUIDriver, conversation_id, marker_for

CID="6af04e14-3e68-83eb-b53b-e4b352c84091"
class Node:
    def __init__(self,role,text,mid=None):
        self.role,self.text,self.mid=role,text,mid
    def get_attribute(self,key):
        return {"data-message-author-role":self.role,"data-message-id":self.mid}.get(key)
    def inner_text(self): return self.text
class Locator:
    def __init__(self,nodes): self.nodes=nodes
    def count(self): return len(self.nodes)
    def nth(self,i): return self.nodes[i]
class Page:
    url="https://chatgpt.com/c/"+CID
    def __init__(self,nodes,stop=False):
        self.nodes,self.stop=nodes,stop
    def locator(self,selector):
        if selector=="[data-message-author-role]": return Locator(self.nodes)
        if selector=='[data-message-author-role="assistant"]':
            return Locator([x for x in self.nodes if x.role=="assistant"])
        if selector=='[data-testid="stop-button"]':
            return Locator([Node("button","stop")] if self.stop else [])
        raise AssertionError(selector)

class DriverObservationTests(unittest.TestCase):
    def test_strict_id(self):
        for bad in ("../x","", "id with spaces", "a"*101):
            with self.assertRaises(ValueError): marker_for(bad)
    def test_reply_must_follow_marker(self):
        p=Page([Node("user","[BATON-WAKE:one] hello"),
                Node("assistant","done","turn-1")])
        d=ChatGPTUIDriver(p,frozenset({CID}))
        self.assertEqual(d.observe_reply(CID,"one").assistant_turn_id,"turn-1")
        p.nodes.insert(1,Node("user","another question"))
        self.assertIsNone(d.observe_reply(CID,"one"))
    def test_streaming_not_complete(self):
        p=Page([Node("user","[BATON-WAKE:one] hello"),
                Node("assistant","partial","turn-1")],stop=True)
        d=ChatGPTUIDriver(p,frozenset({CID}))
        self.assertIsNone(d.observe_reply(CID,"one"))
    def test_duplicate_markers(self):
        p=Page([Node("user","[BATON-WAKE:one]"),
                Node("assistant","done","turn-1"),
                Node("user","[BATON-WAKE:one]")])
        self.assertIsNone(ChatGPTUIDriver(p,frozenset({CID})).observe_reply(CID,"one"))
    def test_exact_readback(self):
        p=Page([Node("assistant","BATON_NEXT C","turn-1")])
        self.assertEqual(ChatGPTUIDriver(p,frozenset({CID})).read_assistant_turn(CID,"turn-1"),"BATON_NEXT C")
    def test_reject_bad_url(self):
        for url in ("https://chatgpt.com:444/c/"+CID,"https://user@chatgpt.com/c/"+CID,
                    "https://chatgpt.com/c/"+CID+"/other"):
            with self.assertRaises(ValueError): conversation_id(url)

if __name__=="__main__": unittest.main()
