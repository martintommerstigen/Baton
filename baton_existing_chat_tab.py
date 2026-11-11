"""Connect an existing ChatGPT conversation to the one installed Baton app.

Preferred: Brave/Chromium's already authenticated ChatGPT tab through Native
Messaging; no extra account sign-in, browser cookies or GitHub transport.
Fallback: embedded QtWebEngine, requiring its own normal browser login.
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
        "preferred_browser": "brave-native-messaging",
    }


def attach_existing_conversation_tab(tabs):
    """Two ways to access an original /c/ conversation, never a blank model."""
    import shutil
    import subprocess
    from PySide6.QtCore import QUrl
    from PySide6.QtWidgets import (
        QApplication, QWidget, QVBoxLayout, QLabel, QPushButton, QMainWindow
    )
    from install_baton_browser_bridge import install_bridge
    tab = QWidget(tabs)
    layout = QVBoxLayout(tab)
    title = QLabel("Brave – bruk akkurat denne eksisterende ChatGPT-samtalen")
    title.setStyleSheet("font-size: 16px; font-weight: 650;")
    layout.addWidget(title)
    hint = QLabel(
        "Baton gir den ChatGPT-samtalen du selv velger tilgang til Greg Core "
        "med dine vanlige Linux-rettigheter. GitHub er ikke mellomledd. "
        "Brave beholder din eksisterende innlogging, historikk og denne chatten. "
        "Brave-broen har en synlig tilkoblingskontroll; i Batons innebygde visning "
        "aktiveres den lokale Core-broen automatisk for den åpne samtalen."
    )
    hint.setWordWrap(True)
    layout.addWidget(hint)
    bridge_path = str(Path(__file__).resolve().parent/"baton_extension")
    details = QLabel(
        "Én gangs tilkobling: Åpne Brave-utvidelser, slå på Utviklermodus, "
        "velg Last inn upakket/Load unpacked og marker mappen:\n" + bridge_path
    )
    details.setWordWrap(True)
    details.setTextInteractionFlags(details.textInteractionFlags() |
                                    details.textInteractionFlags().TextSelectableByMouse)
    layout.addWidget(details)
    start_brave = QPushButton("Åpne Brave-utvidelser (kopier mappeadresse)")
    layout.addWidget(start_brave)
    status = QLabel("Baton Native Messaging registreres når appen starter.")
    status.setWordWrap(True)
    layout.addWidget(status)

    def open_brave_extensions():
        try:
            install_bridge()
        except (OSError, ValueError, PermissionError) as exc:
            status.setText("Lokal registrering feilet: " + type(exc).__name__)
            return
        QApplication.clipboard().setText(bridge_path)
        executable = next(
            (shutil.which(name) for name in
             ("brave-browser", "brave-browser-stable", "brave", "chromium",
              "google-chrome") if shutil.which(name)), None
        )
        if not executable:
            status.setText("Ingen Brave/Chromium funnet. Mappeadressen er kopiert.")
            return
        try:
            subprocess.Popen([executable, "brave://extensions/" if "brave" in executable
                              else "chrome://extensions/"],
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, start_new_session=True)
            status.setText(
                "Mappeadressen er kopiert. Velg Last inn upakket/Load unpacked "
                "og lim inn mappen. Åpne så denne eksisterende ChatGPT-samtalen "
                "i Brave og trykk «Koble denne chatten» i Baton-panelet."
            )
        except OSError:
            status.setText("Nettleseren kunne ikke åpnes. Mappeadressen er kopiert.")

    start_brave.clicked.connect(open_brave_extensions)

    fallback = QLabel(
        "Alternativ: ChatGPT i Batons innebygde nettleservindu. Det bruker en "
        "egen nettleserprofil og kan kreve innlogging på nytt."
    )
    fallback.setWordWrap(True)
    layout.addWidget(fallback)
    button = QPushButton("Åpne eksisterende ChatGPT-samtaler inne i Baton")
    layout.addWidget(button)
    holder = QWidget(tab)
    holder_layout = QVBoxLayout(holder)
    holder_layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(holder, 1)
    opened = [False]

    def open_existing():
        if opened[0]:
            status.setText("Den innebygde ChatGPT-visningen er allerede åpen.")
            return
        if not available_webengine():
            status.setText("QtWebEngine er ikke installert i Batons miljø.")
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
        tab.baton_browser = browser
        tab.baton_profile = profile
        tab.baton_page = page
        opened[0] = True
        button.setEnabled(False)
        view.setUrl(QUrl("https://chatgpt.com/"))
        status.setText(
            "Åpne din eksisterende /c/ samtale. I den innebygde visningen "
            "aktiveres den lokale Core-broen automatisk for den åpne samtalen. "
            "Ingen automatisk adgang til andre chatter."
        )

    button.clicked.connect(open_existing)
    return tab
