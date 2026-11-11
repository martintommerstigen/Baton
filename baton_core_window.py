#!/usr/bin/env python3
"""Baton desktop: single local app for Core, models and communication channels.

The official ChatGPT Linux app remains a separate signed process and is launched
through its public executable, not embedded or modified. Other model providers
will connect through documented APIs/MCP, not scraped website sessions.
"""
import sys
from pathlib import Path


def main():
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import (
        QApplication, QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
        QLabel, QPushButton, QListWidget, QLineEdit, QTextEdit,
        QComboBox, QGroupBox
    )
    from baton_local_runtime import start_local_core, stop_local_core
    from baton_desktop_lease import create_ui_lease, release_ui_lease
    from baton_desktop_shell import (
        launch_official_chatgpt, official_chatgpt_binary, shell_capabilities
    )
    from baton_provider_catalog import provider_catalog
    from baton_outbox import (
        create_store, draft_message, approve_message, get_messages
    )

    app = QApplication(sys.argv)
    core = start_local_core()
    try:
        lease = create_ui_lease()
        outbox = create_store(Path.home() / ".local/state/baton/outbox.sqlite")
    except Exception:
        stop_local_core(core)
        raise

    def shutdown():
        release_ui_lease(lease)
        outbox.close()
        stop_local_core(core)

    app.aboutToQuit.connect(shutdown)
    panel = QWidget()
    panel.setWindowTitle("Baton · modeller, enhet og kanaler")
    panel.setMinimumSize(700, 540)
    root = QVBoxLayout(panel)
    title = QLabel("Baton")
    title.setStyleSheet("font-size: 24px; font-weight: 650;")
    root.addWidget(title)
    summary = QLabel(
        "Én app for modellenes tilkoblinger, Greg Core og kommunikasjon. "
        "Baton gir bare en bekreftet og autorisert modell tilgang til enheten."
    )
    summary.setWordWrap(True)
    root.addWidget(summary)
    tabs = QTabWidget(panel)
    root.addWidget(tabs)

    # The model catalogue is explicit about connected vs planned adapters.
    models = QWidget(tabs)
    models_layout = QVBoxLayout(models)
    models_layout.addWidget(QLabel("Modelltilkoblinger"))
    model_list = QListWidget(models)
    for provider in provider_catalog():
        model_list.addItem(provider.display + " — " + provider.state)
    models_layout.addWidget(model_list)
    model_description = QLabel("Velg en modelltilkobling for detaljer.")
    model_description.setWordWrap(True)
    models_layout.addWidget(model_description)

    def show_provider(index):
        if index < 0:
            return
        provider = provider_catalog()[index]
        model_description.setText(
            provider.display + "\n" + provider.notes +
            "\nTilgang gis først når modellen har en støttet tilkobling "
            "og en eksplisitt autorisert Baton-økt."
        )

    model_list.currentRowChanged.connect(show_provider)
    open_chat = QPushButton("Åpne offisiell ChatGPT")
    chat_status = QLabel("")
    chat_status.setWordWrap(True)

    def open_official_client():
        result = launch_official_chatgpt()
        if result["ok"]:
            chat_status.setText(
                "ChatGPT-appen ble forsøkt startet. "
                "MCP må fortsatt være aktivert i ChatGPTs innstillinger."
            )
        else:
            chat_status.setText(
                "Offisiell ChatGPT-klient ikke funnet. "
                "Installer den fra OpenAI og registrer Baton MCP."
            )

    open_chat.clicked.connect(open_official_client)
    models_layout.addWidget(open_chat)
    models_layout.addWidget(chat_status)
    tabs.addTab(models, "Modeller")

    # An auditable outbox is not an external transport. The local user must
    # explicitly approve a draft, and approval is not equivalent to delivery.
    channels = QWidget(tabs)
    channels_layout = QVBoxLayout(channels)
    channels_layout.addWidget(QLabel("Meldinger og kanaler"))
    channel_form = QGroupBox("Nytt utkast")
    form = QVBoxLayout(channel_form)
    channel_kind = QComboBox(channel_form)
    for kind, display in (
        ("model", "Modell ↔ modell"),
        ("chat", "Direktemelding"),
        ("email", "E-post"),
        ("forum", "Forum"),
        ("social", "Sosiale medier"),
    ):
        channel_kind.addItem(display, kind)
    recipient = QLineEdit(channel_form)
    recipient.setPlaceholderText("Mottaker / kanal-ID")
    body = QTextEdit(channel_form)
    body.setPlaceholderText("Meldingstekst")
    body.setMaximumHeight(90)
    form.addWidget(channel_kind)
    form.addWidget(recipient)
    form.addWidget(body)
    draft = QPushButton("Opprett utkast")
    approve = QPushButton("Godkjenn valgt utkast")
    form_actions = QHBoxLayout()
    form_actions.addWidget(draft)
    form_actions.addWidget(approve)
    form.addLayout(form_actions)
    channels_layout.addWidget(channel_form)
    outbox_list = QListWidget(channels)
    channels_layout.addWidget(outbox_list)
    outbox_status = QLabel(
        "Ingen ekstern transport er koblet til. Godkjenning sender ingen melding."
    )
    outbox_status.setWordWrap(True)
    channels_layout.addWidget(outbox_status)
    indexed = []

    def refresh_outbox():
        indexed.clear()
        outbox_list.clear()
        for record in get_messages(outbox):
            indexed.append(record)
            outbox_list.addItem(
                record["state"].upper() + " · " + record["channel_kind"] +
                " · " + record["recipient"] + " · " + record["body"][:65]
            )

    def make_draft():
        try:
            mid = draft_message(
                outbox, channel_kind.currentData(), recipient.text(),
                body.toPlainText(), "local-baton-operator"
            )
        except ValueError as exc:
            outbox_status.setText("Utkast avvist: " + str(exc))
            return
        outbox_status.setText("Utkast " + mid[:8] + " lagret lokalt. IKKE sendt.")
        recipient.clear()
        body.clear()
        refresh_outbox()

    def approve_selected():
        index = outbox_list.currentRow()
        if index < 0 or index >= len(indexed):
            outbox_status.setText("Velg et utkast først.")
            return
        try:
            approve_message(outbox, indexed[index]["message_id"])
        except ValueError as exc:
            outbox_status.setText("Kan ikke godkjenne: " + str(exc))
            return
        outbox_status.setText(
            "Godkjent lokalt. Ingen ekstern transport er koblet til; "
            "ingen leveringspåstand."
        )
        refresh_outbox()

    draft.clicked.connect(make_draft)
    approve.clicked.connect(approve_selected)
    refresh_outbox()
    tabs.addTab(channels, "Kanaler")

    # The central authority remains the installed device's own local Core.
    device = QWidget(tabs)
    device_layout = QVBoxLayout(device)
    device_status = QLabel(
        "Baton Core: startet på 127.0.0.1:52526\n"
        "Rettigheter: vanlig Linux-bruker, ikke root\n"
        "MCP: krever tilkoblet og autorisert modellklient\n"
        "Skriving: mulig via Core, men må bekreftes med faktisk resultat og lesetest\n"
        "Ekstern publisering: ikke konfigurert"
    )
    device_status.setWordWrap(True)
    device_layout.addWidget(device_status)
    stop = QPushButton("Stopp Baton og trekk tilbake ny verktøytilgang")
    stop.clicked.connect(panel.close)
    device_layout.addWidget(stop)
    device_layout.addStretch(1)
    tabs.addTab(device, "Enhet og tilgang")
    panel.show()

    if official_chatgpt_binary() is not None:
        chat_status.setText("Offisiell ChatGPT-klient er tilgjengelig.")
        # Baton provides one startup: open a supported client automatically.
        QTimer.singleShot(500, open_official_client)
    else:
        chat_status.setText(
            "Offisiell ChatGPT-klient er ikke installert. "
            "Baton Core og lokale kanaler kan fortsatt brukes."
        )
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
