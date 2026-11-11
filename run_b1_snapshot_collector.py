"""B1 local-only snapshot collector. NEVER clicks Send or opens a browser.

Run as a dedicated unprivileged collector UID with exclusive CDP access.
The observer must run under a different UID with NO access to CDP. The
collector exposes only fixed source-turn snapshots on an AF_UNIX socket.
"""
import argparse

from b1_snapshot_relay import SnapshotServer
from chatgpt_ui_driver import ChatGPTUIDriver, PAUSE_FILE, pause_active
from observe_verified_broker_source import select_existing_source
from run_chatgpt_wake import local_cdp


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    for arg in ("source", "target", "socket", "observer-uid"):
        p.add_argument("--" + arg, required=True)
    p.add_argument("--cdp", default="http://127.0.0.1:9222")
    a = p.parse_args(argv)
    local_cdp(a.cdp)
    if pause_active(PAUSE_FILE):
        raise RuntimeError("PAUSE_UI_WRITES active or untrusted")
    try:
        observer_uid = int(a.observer_uid)
    except ValueError:
        p.error("observer UID must be integer")
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(a.cdp)
        page = select_existing_source(browser, a.source)
        driver = ChatGPTUIDriver(page, frozenset({a.source}))
        with SnapshotServer(a.socket, reader=driver, source_id=a.source,
                            allowed_targets=frozenset({a.target}), observer_uid=observer_uid,
                            pause_checker=lambda: pause_active(PAUSE_FILE)) as server:
            server.serve_forever(poll_interval=0.2)


if __name__ == "__main__":
    main()
