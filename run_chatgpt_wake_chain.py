"""Explicitly authorized two-hop existing-chat wake test (no background daemon).

Requires THREE already open logged-in ChatGPT tabs for A, B and C,
local CDP, and a predetermined C message. The assistant in B must emit BATON_NEXT <C UUID>.
No model-generated body or arbitrary command is executed.
"""
import argparse
import hashlib
import json
import time
from pathlib import Path
from urllib.parse import urlparse
from wake_contract import WakeLedger
from wake_chain import ChainPlan, run_chain
from wake_origin import verify_source_turn, discover_source_turn
from chatgpt_ui_driver import ChatGPTUIDriver, conversation_id
from run_chatgpt_wake import local_cdp
from wake_ui_lock import ui_controller_lock

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
    p.add_argument('--source-turn-id',
                   help='DOM assistant turn ID in the EXISTING A chat containing BATON_WAKE B FIRST_ID')
    p.add_argument('--wait-source-seconds',type=int,default=120,
                   help='Poll the already-open A tab for its exact wake request')
    p.add_argument('--cdp',default='http://127.0.0.1:9222')
    args=p.parse_args(argv)
    local_cdp(args.cdp)
    if not 0 <= args.wait_source_seconds <= 3600:
        p.error('--wait-source-seconds must be between 0 and 3600')
    if Path('/home/olliver/GTRCM-newborn-bootstrap/transport/PAUSE_UI_WRITES').exists():
        raise RuntimeError('UI writes paused')
    from playwright.sync_api import sync_playwright
    # One host lock covers both runners even when their SQLite DB paths differ.
    with ui_controller_lock():
      with sync_playwright() as pw:
          browser=pw.chromium.connect_over_cdp(args.cdp)
          pages=select_pages(browser,(args.a,args.b,args.c))
          class WaitDriver:
              def __init__(self, driver): self.driver=driver
              def submit_once(self,*args): return self.driver.submit_once(*args)
              def observe_reply(self,chat,message_id,digest):
                  deadline=time.monotonic()+120
                  while True:
                      result=self.driver.observe_reply(chat,message_id,digest)
                      if result is not None: return result
                      if time.monotonic()>=deadline: return None
                      time.sleep(1)
          drivers={chat:ChatGPTUIDriver(page,frozenset({chat})) for chat,page in pages.items()}
          source_turn_id=args.source_turn_id
          if not source_turn_id:
              deadline=time.monotonic()+args.wait_source_seconds
              while True:
                  source_turn_id=discover_source_turn(drivers[args.a],args.a,args.b,args.first_id)
                  if source_turn_id is not None: break
                  if time.monotonic()>=deadline:
                      raise RuntimeError('No verified A source request; no UI submission')
                  time.sleep(1)
          verify_source_turn(drivers[args.a],args.a,source_turn_id,args.b,args.first_id)
          waiting={chat:WaitDriver(driver) for chat,driver in drivers.items()}
          plan=ChainPlan(args.a,args.b,args.c,args.first_id,args.second_id,
                         args.first_body,args.second_body,
                         hashlib.sha256(args.first_body.encode()).hexdigest(),
                         hashlib.sha256(args.second_body.encode()).hexdigest(),
                         source_turn_id)
          ledger=WakeLedger(args.db)
          result=run_chain(ledger,waiting[args.b],waiting[args.c],plan,
                           drivers[args.b].read_assistant_turn)
          first_receipt=ledger.provenance(args.first_id)
          second_receipt=ledger.provenance(args.second_id)
          def receipt(row):
              if row is None: return None
              source,target,source_turn,digest,state,observed_turn,updated=row
              return {'source_chat':source,'target_chat':target,
                      'source_turn_id':source_turn,'target_assistant_turn_id':observed_turn,
                      'state':state,'updated_unix':updated}
          print(json.dumps({'source_chat':args.a,'source_turn_id':source_turn_id,
                            'source_request':'verified_in_existing_chat',
                            'a_to_b_receipt':receipt(first_receipt),
                            'b_to_c_receipt':receipt(second_receipt),**result}))
          # Leave the operator's authenticated browser and tabs untouched.

if __name__=='__main__': main()
