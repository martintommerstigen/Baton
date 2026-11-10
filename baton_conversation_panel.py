"""Always-visible native Baton controls beside the embedded ChatGPT web view.

No model tool registration is implied by this UI. Sending is an explicit local
user action; a DOM click is not a verified conversation delivery or wake.
"""
import re
from urllib.parse import urlparse
from baton_chatgpt_view import conversation_url, is_chatgpt_conversation_url
from baton_embedded_send import prepare_send_script, send_click_script

CHAT_PATH = re.compile(r"^/c/([0-9a-f]{8}-[0-9a-f-]{20,64})$", re.I)


def chat_id_from_url(url):
    """Return the observed exact ChatGPT conversation ID, or None."""
    if not isinstance(url, str):
        return None
    try:
        parsed = urlparse(url)
        matched = CHAT_PATH.fullmatch(parsed.path)
        if not matched:
            return None
        chat_id = matched.group(1)
        return chat_id if is_chatgpt_conversation_url(url, chat_id) else None
    except (ValueError, TypeError):
        return None


def attach_baton_panel(window, view, page, *, initial_chat=None, initial_message=None):
    """Attach the native control dock, independently of the ChatGPT website."""
    from PySide6.QtCore import QUrl, Qt
    from PySide6.QtWidgets import (
        QApplication, QDockWidget, QWidget, QVBoxLayout, QHBoxLayout,
        QLabel, QLineEdit, QPlainTextEdit, QPushButton
    )

    dock = QDockWidget("Baton · Samtalestafett", window)
    dock.setObjectName("baton-conversation-dock")
    dock.setAllowedAreas(Qt.DockWidgetArea.RightDockWidgetArea |
                         Qt.DockWidgetArea.LeftDockWidgetArea)
    body = QWidget(dock)
    layout = QVBoxLayout(body)
    layout.addWidget(QLabel("Mottaker · eksisterende samtale-ID"))
    recipient = QLineEdit(initial_chat or "")
    recipient.setObjectName("baton-recipient")
    recipient.setPlaceholderText("xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx")
    layout.addWidget(recipient)
    recipient_actions = QHBoxLayout()
    use_current = QPushButton("Bruk åpen samtale")
    open_target = QPushButton("Åpne mottaker")
    recipient_actions.addWidget(use_current)
    recipient_actions.addWidget(open_target)
    layout.addLayout(recipient_actions)

    layout.addWidget(QLabel("Melding fra Baton"))
    message = QPlainTextEdit()
    message.setObjectName("baton-message")
    message.setPlaceholderText("Skriv en melding til en eksisterende samtale")
    message.setPlainText(initial_message or "")
    message.setMinimumHeight(135)
    layout.addWidget(message)
    send = QPushButton("Send til mottaker")
    send.setObjectName("baton-send")
    copy = QPushButton("Kopier melding")
    status = QLabel("Klar. Sending krever et klikk og riktig samtale.")
    status.setWordWrap(True)
    status.setObjectName("baton-status")
    layout.addWidget(send)
    layout.addWidget(copy)
    layout.addWidget(status)
    layout.addStretch(1)
    dock.setWidget(body)
    window.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
    dock.setMinimumWidth(300)

    # Keep a confirmed click from being sent twice after network/UI uncertainty.
    attempted = set()
    in_flight = [False]

    def set_status(value):
        status.setText(value)

    def current_id():
        return chat_id_from_url(view.url().toString())

    def use_current_chat():
        chat_id = current_id()
        if chat_id:
            recipient.setText(chat_id)
            set_status("Åpen samtale registrert som mottaker.")
        else:
            set_status("Åpne en eksisterende ChatGPT-samtale først.")

    def open_recipient():
        try:
            url = conversation_url(recipient.text().strip())
        except ValueError:
            set_status("Ugyldig samtale-ID.")
            return
        view.setUrl(QUrl(url))
        set_status("Åpner mottaker. Ingen melding er sendt.")

    def copy_message():
        QApplication.clipboard().setText(message.toPlainText())
        set_status("Meldingen kopiert. Ingen melding er sendt.")

    def refresh_send():
        chat_id = recipient.text().strip()
        can_send = (
            not in_flight[0] and bool(message.toPlainText().strip())
            and is_chatgpt_conversation_url(view.url().toString(), chat_id)
            and (chat_id, message.toPlainText()) not in attempted
        )
        send.setEnabled(can_send)

    def on_url_change(url):
        observed = chat_id_from_url(url.toString())
        if observed and not recipient.text().strip():
            recipient.setText(observed)
        refresh_send()

    def send_message():
        chat_id = recipient.text().strip()
        text = message.toPlainText()
        if not is_chatgpt_conversation_url(view.url().toString(), chat_id):
            set_status("STOPP: Åpen ChatGPT-samtale er ikke valgt mottaker.")
            refresh_send()
            return
        try:
            script = prepare_send_script(text)
        except ValueError:
            set_status("Ugyldig melding (1–4000 tegn).")
            return
        if (chat_id, text) in attempted or in_flight[0]:
            set_status("Denne meldingen er allerede forsøkt. Ingen automatisk gjensending.")
            return
        in_flight[0] = True
        refresh_send()
        set_status("Forbereder melding i riktig samtale ...")

        def prepared(result):
            if not isinstance(result, dict) or not result.get("ok"):
                in_flight[0] = False
                set_status("Kunne ikke fylle meldingsfeltet. Ingen sending: " +
                           (str(result.get("reason")) if isinstance(result, dict) else "ukjent feil"))
                refresh_send()
                return
            if not is_chatgpt_conversation_url(view.url().toString(), chat_id):
                in_flight[0] = False
                set_status("STOPP: Samtalen endret seg før sending.")
                refresh_send()
                return

            def clicked(result):
                in_flight[0] = False
                if isinstance(result, dict) and result.get("ok"):
                    attempted.add((chat_id, text))
                    set_status("Sendeknappen ble klikket én gang. Levering/svar IKKE verifisert.")
                else:
                    set_status("Sendeknappen var ikke klar. Levering IKKE verifisert.")
                refresh_send()
            page.runJavaScript(send_click_script(), clicked)
        page.runJavaScript(script, prepared)

    use_current.clicked.connect(use_current_chat)
    open_target.clicked.connect(open_recipient)
    copy.clicked.connect(copy_message)
    send.clicked.connect(send_message)
    view.urlChanged.connect(on_url_change)
    recipient.textChanged.connect(lambda _: refresh_send())
    message.textChanged.connect(refresh_send)
    refresh_send()
    # Keep Qt objects attached to dock for lifetime of the app.
    dock.baton_controls = {
        "recipient": recipient, "message": message, "send": send,
        "status": status, "use_current": use_current, "open_target": open_target
    }
    return dock
