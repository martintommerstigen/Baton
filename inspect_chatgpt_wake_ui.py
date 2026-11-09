"""Read-only UI readiness inspection for existing ChatGPT tabs.

No clicks, no edits, no screenshots, no cookie reads and no network requests.
Reports selector presence only. An observed selector is not proof of send success.
"""
import argparse
import json
from chatgpt_ui_driver import conversation_id
from run_chatgpt_wake import local_cdp


def inspect_page(page):
    cid=conversation_id(page.url)
    editor=page.locator("#prompt-textarea")
    send=page.locator('[data-testid="send-button"]')
    turns=page.locator('[data-message-author-role]')
    assistant=page.locator('[data-message-author-role="assistant"]')
    ids=[assistant.nth(i).get_attribute("data-message-id")
         for i in range(assistant.count())]
    return {
        "conversation_id":cid,
        "composer_unique":editor.count()==1,
        "composer_visible":editor.count()==1 and editor.is_visible(),
        "send_button_unique":send.count()==1,
        "send_button_enabled":send.count()==1 and send.is_enabled(),
        "turn_count":turns.count(),
        "assistant_turns":assistant.count(),
        "assistant_turn_ids_present":sum(bool(i) for i in ids),
    }


def inspect_browser(browser, targets):
    result={target:[] for target in targets}
    for ctx in browser.contexts:
        for page in ctx.pages:
            try:
                cid=conversation_id(page.url)
            except ValueError:
                continue
            if cid in result:
                result[cid].append(inspect_page(page))
    return {
        "targets":{target:{"tab_count":len(result[target]),
                           "inspection":result[target][0] if len(result[target])==1 else None}
                   for target in targets},
        "ready":all(len(result[t])==1
                    and result[t][0]["composer_unique"]
                    and result[t][0]["composer_visible"]
                    and result[t][0]["send_button_unique"]
                    and result[t][0]["assistant_turn_ids_present"]>0
                    for t in targets),
    }


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--target",action="append",required=True)
    p.add_argument("--cdp",default="http://127.0.0.1:9222")
    args=p.parse_args(argv)
    local_cdp(args.cdp)
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser=pw.chromium.connect_over_cdp(args.cdp)
        print(json.dumps(inspect_browser(browser,args.target),sort_keys=True))
        browser.close()


if __name__=="__main__":
    main()
