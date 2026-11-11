"""Existing ChatGPT conversations inside the one installed Baton app.

This is a local, opt-in DOM-mediated tool transport for the *real existing*
ChatGPT conversation, not a fresh OAuth/Responses model request. The selected
conversation keeps its ChatGPT history and account context. Native MCP tools
still require the target ChatGPT client's separate product support.
"""
from pathlib import Path


def browser_profile_directory(home=None):
    base = Path(home) if home is not None else Path.home()
    return base / ".local/share/baton/chatgpt-profile"


def available_webengine():
    try:
        from PySide6.QtWebEngineWidgets import QWebEngineView
        from PySide6.QtWebEngineCore import QWebEnginePage
        return bool(QWebEngineView and QWebEnginePage)
    except (ImportError, OSError):
        return False


def describe_connection():
    return {
        "conversation": "existing-chatgpt-chat",
        "transport": "direct-local-core-dom-bridge",
        "github_runtime": False,
        "native_chatgpt_mcp": False,
        "user_opt_in_required": True,
        "automatic_wake": False,
    }


def attach_existing_conversation_tab(tabs):
    """Build one tab with a lazily loaded real ChatGPT web session."""
    from PySide6.QtCore import QUrl
    from PySide6.QtWidgets import (
        QWidget, QVBoxLayout, QLabel, QPushButton, QMainWindow
    )
    tab = QWidget(tabs)
    layout = QVBoxLayout(tab)
    hint = QLabel(
        "Bruk dine eksisterende ChatGPT-samtaler, med historikk og kontekst. "
        "Baton kobler seg lokalt til Greg Core, uten GitHub og uten ny "
        "Responses API-samtale. Når du åpner en eksisterende samtale mens "
        "Baton kjører, aktiveres den lokale Core-broen automatisk for akkurat "
        "den samtalen. Dette er en lokal tekstprotokoll – ikke et innebygd "
        "ChatGPT-verktøy."
    )
    hint.setWordWrap(True)
    layout.addWidget(hint)
    button = QPushButton("Åpne mine eksisterende ChatGPT-samtaler")
    layout.addWidget(button)
    status = QLabel(
        "ChatGPT kan be om innlogging én gang i Batons separate, vedvarende "
        "nettleserprofil. Dette endrer ikke innloggingen i Brave."
    )
    status.setWordWrap(True)
    layout.addWidget(status)
    holder = QWidget(tab)
    holder_layout = QVBoxLayout(holder)
    holder_layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(holder, 1)
    opened = [False]

    def open_existing():
        if opened[0]:
            status.setText("Åpne en samtale i sidepanelet og aktiver Baton-verktøy.")
            return
        if not available_webengine():
            status.setText(
                "Mangler QtWebEngine. Start Baton på nytt etter installasjon "
                "av PySide6 WebEngine i Batons eget miljø."
            )
            return
        from PySide6.QtWebEngineCore import QWebEngineProfile, QWebEnginePage
        from PySide6.QtWebEngineWidgets import QWebEngineView
        from baton_conversation_panel import attach_baton_panel

        profile = QWebEngineProfile("baton-chatgpt", tab)
        storage = browser_profile_directory()
        storage.mkdir(parents=True, exist_ok=True)
        profile.setPersistentStoragePath(str(storage))
        profile.setCachePath(str(storage / "cache"))
        profile.setPersistentCookiesPolicy(
            QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies
        )
        browser = QMainWindow(holder)
        browser.setWindowTitle("Baton · eksisterende ChatGPT-samtaler")
        view = QWebEngineView(browser)
        page = QWebEnginePage(profile, view)
        view.setPage(page)
        browser.setCentralWidget(view)
        attach_baton_panel(browser, view, page)
        holder_layout.addWidget(browser)
        # Retain Qt native ownership across tab changes.
        tab.baton_browser = browser
        tab.baton_profile = profile
        tab.baton_page = page
        opened[0] = True
        button.setEnabled(False)
        view.setUrl(QUrl("https://chatgpt.com/"))
        status.setText(
            "Velg en eksisterende ChatGPT-samtale i sidepanelet. "
            "Baton aktiverer Core-broen automatisk for den åpne samtalen. "
            "Stopp-knappen kan trekke tilbake tilgangen; ikke naviger bort "
            "mens en kommando utføres."
        )

    button.clicked.connect(open_existing)
    return tab
