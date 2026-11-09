"""Explicitly authorized two-hop existing-chat wake test (no background daemon).

Requires TWO already open logged-in ChatGPT tabs for B and C, local CDP,
and a predetermined C message. The assistant in B must emit BATON_NEXT <C UUID>.
No model-generated body or arbitrary command is executed.
"""
import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import urlparse
from wake_contract import WakeLedger
from wake_chain import ChainPlan, run_chain
from chatgpt_ui_driver import ChatGPTUIDriver, conversation_id
from run_chatgpt_wake import local_cdp

def select_pages(browser, ids):
    found={x:[] for x in ids}
    for ctx in browser.contexts:
        for page in ctx.pages:
            try: chat=conversation_id(page.url)
            except ValueError: continue
            if chat in found: found[chat].append(page)
    if any(len(pages)!=1 for pages in found.values()):
        raise RuntimeError('Each target must have exactly one already-open tab')
    return {chat:pages[0] for chat,pages in found.items()}

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('a','b','c','first-id','second-id','db','first-body','second-body'):
        p.add_argument('--'+name,required=True)
    p.add_argument('--cdp',default='http://127.0.0.1:9222')
    args=p.parse_args(argv)
    local_cdp(args.cdp)
    if Path('/home/olliver/GTRCM-newborn-bootstrap/transport/PAUSE_UI_WRITES').exists():
        raise RuntimeError('UI writes paused')
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser=pw.chromium.connect_over_cdp(args.cdp)
        pages=select_pages(browser,(args.b,args.c))
        drivers={chat:ChatGPTUIDriver(page,frozenset({chat})) for chat,page in pages.items()}
        plan=ChainPlan(args.a,args.b,args.c,args.first_id,args.second_id,
                       args.first_body,args.second_body,
                       hashlib.sha256(args.first_body.encode()).hexdigest(),
                       hashlib.sha256(args.second_body.encode()).hexdigest())
        ledger=WakeLedger(args.db)
        result=run_chain(ledger,drivers[args.b],drivers[args.c],plan,
                         drivers[args.b].read_assistant_turn)
        print(json.dumps(result))
        browser.close()

if __name__=='__main__': main()
