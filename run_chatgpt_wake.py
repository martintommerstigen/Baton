"""Run one explicitly authorized wake on an ALREADY OPEN existing ChatGPT tab.

Requires: pip install playwright; a browser already exposing local CDP.
Never launches browser, logs in, opens new chats or extracts cookies.
Example:
 python run_chatgpt_wake.py --target CHAT_UUID --source SOURCE_UUID \
   --id unique-id --body "Har du mottatt Baton?" --db ./wake.sqlite3
Use --reconcile --id unique-id to inspect an uncertain send without resending.
"""
import argparse
import json
from urllib.parse import urlparse
from wake_contract import WakeLedger
from wake_adapter import wake_once, reconcile
from chatgpt_ui_driver import ChatGPTUIDriver, conversation_id

def local_cdp(url):
    p=urlparse(url)
    if p.scheme!='http' or p.hostname not in ('127.0.0.1','localhost','::1') or p.username or p.password:
        raise ValueError('CDP must be local HTTP only')
    return url

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cdp',default='http://127.0.0.1:9222')
    p.add_argument('--db',required=True)
    p.add_argument('--id',required=True)
    p.add_argument('--target',required=True)
    p.add_argument('--source')
    p.add_argument('--body')
    p.add_argument('--reconcile',action='store_true')
    args=p.parse_args(argv)
    local_cdp(args.cdp)
    if not args.reconcile and (not args.source or not args.body):
        p.error('--source and --body required unless --reconcile')
    from playwright.sync_api import sync_playwright
    ledger=WakeLedger(args.db)
    with sync_playwright() as pw:
        browser=pw.chromium.connect_over_cdp(args.cdp)
        pages=[page for context in browser.contexts for page in context.pages]
        matching=[]
        for page in pages:
            try:
                if conversation_id(page.url)==args.target: matching.append(page)
            except ValueError: pass
        if len(matching)!=1:
            raise RuntimeError('Require exactly one ALREADY OPEN target conversation tab')
        driver=ChatGPTUIDriver(matching[0],frozenset({args.target}))
        if args.reconcile:
            result=reconcile(ledger,driver,args.id)
        else:
            import hashlib
            digest=hashlib.sha256(args.body.encode('utf-8')).hexdigest()
            result=wake_once(ledger,driver,args.id,args.source,args.target,digest,args.body)
        print(json.dumps({'message_id':args.id,'state':result,'target':args.target}))
        # CDP disconnect; do not close the user's browser.
        browser.close()

if __name__=='__main__': main()
