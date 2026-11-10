"""Baton-integrated ChatGPT view (optional PySide6 QtWebEngine dependency).

Runs ChatGPT *inside* a Baton-owned window with a persistent, local browser
profile. No cookie extraction, DOM injection, or automated UI writes.
"""
import re
from urllib.parse import urlparse

CHAT_ID = re.compile(r"^[0-9a-f]{8}-[0-9a-f-]{20,64}$", re.I)

def conversation_url(chat_id):
    if not isinstance(chat_id, str) or not CHAT_ID.fullmatch(chat_id):
        raise ValueError("invalid conversation ID")
    return "https://chatgpt.com/c/" + chat_id

def is_chatgpt_conversation_url(url, chat_id):
    parsed = urlparse(url)
    return (parsed.scheme == "https" and parsed.hostname == "chatgpt.com"
            and parsed.username is None and parsed.password is None
            and parsed.port in (None, 443)
            and parsed.path == "/c/" + chat_id
            and not parsed.query and not parsed.fragment)

def main():
    import argparse
    from pathlib import Path
    parser = argparse.ArgumentParser(description="Baton embedded ChatGPT")
    parser.add_argument("--chat-id", help="Open a known existing ChatGPT conversation")
    args = parser.parse_args()
    target = conversation_url(args.chat_id) if args.chat_id else "https://chatgpt.com/"
    try:
        from PySide6.QtCore import QUrl
        from PySide6.QtWidgets import QApplication, QMainWindow
        from PySide6.QtWebEngineCore import QWebEngineProfile
        from PySide6.QtWebEngineWidgets import QWebEngineView
    except ImportError as exc:
        raise SystemExit("Requires PySide6 and PySide6-Addons (QtWebEngine): "+str(exc))
    app = QApplication([])
    profile = QWebEngineProfile("baton-chatgpt", app)
    storage = Path.home()/".local/share/baton/chatgpt-profile"
    storage.mkdir(parents=True,exist_ok=True)
    profile.setPersistentStoragePath(str(storage))
    profile.setCachePath(str(storage/"cache"))
    profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies)
    from PySide6.QtWebEngineCore import QWebEnginePage
    view = QWebEngineView()
    page = QWebEnginePage(profile,view)
    view.setPage(page)
    window = QMainWindow()
    window.setWindowTitle("Baton · ChatGPT")
    window.setCentralWidget(view)
    window.resize(1200,800)
    view.setUrl(QUrl(target))
    window.show()
    return app.exec()

if __name__ == "__main__":
    raise SystemExit(main())
