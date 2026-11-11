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
        QComboBox, QGroupBox, QCheckBox
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
    from baton_attention import (
        setup_attention, get_mode, set_mode, set_rule, remove_rule, list_rules,
        decide, receive, list_inbox, recent_audit, prune
    )
    from uuid import uuid4

    app = QApplication(sys.argv)
    core = start_local_core()
    try:
        lease = create_ui_lease()
        outbox = create_store(Path.home() / ".local/state/baton/outbox.sqlite")
        setup_attention(outbox)
        prune(outbox)
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

    # Working model-neutral chat: local Ollama or a chosen HTTPS
    # OpenAI-compatible endpoint, without scraping website accounts.
    # This plain-text answer never becomes an executable Greg command.
    from queue import Queue, Empty
    from threading import Thread
    from baton_model_clients import chat_completion

    model_chat = QWidget(tabs)
    chat_layout = QVBoxLayout(model_chat)
    chat_layout.addWidget(QLabel("Samtale med lokal eller API-tilkoblet modell"))
    endpoint = QLineEdit(model_chat)
    endpoint.setText("http://127.0.0.1:11434/v1/chat/completions")
    endpoint.setPlaceholderText("OpenAI-kompatibelt /chat/completions-endepunkt")
    model_id = QLineEdit(model_chat)
    model_id.setPlaceholderText("Modell-ID hos valgt leverandør")
    api_secret = QLineEdit(model_chat)
    api_secret.setEchoMode(QLineEdit.EchoMode.Password)
    api_secret.setPlaceholderText("API-nøkkel (valgfri; bare i denne økten)")
    chat_layout.addWidget(endpoint)
    chat_layout.addWidget(model_id)
    chat_layout.addWidget(api_secret)
    transcript = QTextEdit(model_chat)
    transcript.setReadOnly(True)
    chat_layout.addWidget(transcript)
    model_prompt = QTextEdit(model_chat)
    model_prompt.setPlaceholderText("Skriv til modellen")
    model_prompt.setMaximumHeight(100)
    chat_layout.addWidget(model_prompt)
    send_to_model = QPushButton("Send til modell")
    chat_layout.addWidget(send_to_model)
    model_result = QLabel(
        "Denne tilkoblingen bruker et dokumentert API, ikke innlogging "
        "eller scraping av en annen leverandørs ChatGPT-nettside."
    )
    model_result.setWordWrap(True)
    chat_layout.addWidget(model_result)
    model_results = Queue()
    model_busy = [False]

    def send_model_prompt():
        if model_busy[0]:
            return
        question = model_prompt.toPlainText()
        if not question.strip():
            model_result.setText("Skriv en melding først.")
            return
        endpoint_url, model_name = endpoint.text(), model_id.text()
        token = api_secret.text().strip() or None
        model_busy[0] = True
        send_to_model.setEnabled(False)
        model_result.setText("Venter på modellen ...")
        transcript.append("Du: " + question)
        model_prompt.clear()

        def perform():
            try:
                reply = chat_completion(endpoint_url, model_name, question,
                                        bearer=token, timeout=45)
                model_results.put(("ok", reply))
            except (OSError, ValueError, RuntimeError) as exc:
                model_results.put(("error", type(exc).__name__ + ": " + str(exc)))
        Thread(target=perform, name="baton-model-chat", daemon=True).start()

    def poll_model_results():
        try:
            status, payload = model_results.get_nowait()
        except Empty:
            return
        model_busy[0] = False
        send_to_model.setEnabled(True)
        if status == "ok":
            transcript.append("Modell: " + payload)
            model_result.setText("Modellsvar mottatt lokalt i Baton.")
        else:
            model_result.setText("Modellforespørsel feilet: " + payload)

    send_to_model.clicked.connect(send_model_prompt)
    model_poller = QTimer(panel)
    model_poller.setInterval(180)
    model_poller.timeout.connect(poll_model_results)
    model_poller.start()
    tabs.addTab(model_chat, "Modellsamtale")

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

    # Recipient-controlled selective attention is local Core policy, not a
    # cloud moderation claim. Transport adapters must provide authenticated
    # sender IDs and recipient-side topic classification themselves.
    attention_owner = "local:" + Path.home().name
    filters = QWidget(tabs)
    filters_layout = QVBoxLayout(filters)
    filters_layout.addWidget(QLabel("Hva vil du slippe gjennom?"))
    explanation = QLabel(
        "Reglene gjelder for én lokal mottaker. Blokkert innhold lagres ikke. "
        "Dempet innhold vises ikke i vanlig innboks og slettes etter ett døgn. "
        "Identitetsregler må bruke leverandør:stabil-ID, ikke bare et visningsnavn. "
        "Ekstern mottakstransport er ennå ikke tilkoblet; testpanelet under er lokalt."
    )
    explanation.setWordWrap(True)
    filters_layout.addWidget(explanation)
    mode_row = QHBoxLayout()
    mode_row.addWidget(QLabel("Slipp gjennom"))
    attention_mode = QComboBox(filters)
    attention_mode.addItem("Alle uten blokkeringsregel", "open")
    attention_mode.addItem("Bare eksplisitt tillatte (øvrige dempes)", "allowlist")
    attention_mode.setCurrentIndex(0 if get_mode(outbox, attention_owner) == "open" else 1)
    mode_row.addWidget(attention_mode)
    filters_layout.addLayout(mode_row)

    filter_row = QHBoxLayout()
    dimension = QComboBox(filters)
    for key, label in (
        ("identity", "Individuasjon (leverandør:ID)"),
        ("topic", "Temaetikett"),
        ("keyword", "Ord eller uttrykk i innhold")
    ):
        dimension.addItem(label, key)
    pattern = QLineEdit(filters)
    pattern.setPlaceholderText("Individuasjon eller tema / uttrykk")
    action = QComboBox(filters)
    for key, label in (("allow", "Slipp gjennom"),
                       ("mute", "Demp"), ("block", "Blokker")):
        action.addItem(label, key)
    add_filter = QPushButton("Lagre regel")
    filter_row.addWidget(dimension)
    filter_row.addWidget(pattern)
    filter_row.addWidget(action)
    filter_row.addWidget(add_filter)
    filters_layout.addLayout(filter_row)
    filter_list = QListWidget(filters)
    filter_list.setMaximumHeight(115)
    filters_layout.addWidget(filter_list)
    remove_filter = QPushButton("Fjern markert regel")
    filters_layout.addWidget(remove_filter)
    filter_status = QLabel("")
    filter_status.setWordWrap(True)
    filters_layout.addWidget(filter_status)
    cached_rules = []

    def refresh_rules():
        cached_rules.clear()
        filter_list.clear()
        for rule in list_rules(outbox, attention_owner):
            cached_rules.append(rule)
            filter_list.addItem(
                rule["action"].upper() + " · " + rule["dimension"] +
                " · " + rule["pattern"]
            )

    def change_attention_mode(index):
        try:
            set_mode(outbox, attention_owner, attention_mode.itemData(index))
            filter_status.setText("Filtermodus lagret for denne lokale mottakeren.")
        except ValueError as exc:
            filter_status.setText("Avvist: " + str(exc))

    def add_attention_rule():
        try:
            rule_id = set_rule(outbox, attention_owner, dimension.currentData(),
                               pattern.text(), action.currentData())
            filter_status.setText("Regel lagret: " + rule_id[:8])
            pattern.clear()
            refresh_rules()
        except ValueError as exc:
            filter_status.setText("Avvist: " + str(exc))

    def delete_attention_rule():
        index = filter_list.currentRow()
        if index < 0 or index >= len(cached_rules):
            filter_status.setText("Velg en regel først.")
            return
        if remove_rule(outbox, attention_owner, cached_rules[index]["rule_id"]):
            filter_status.setText("Regel slettet lokalt.")
        refresh_rules()

    attention_mode.currentIndexChanged.connect(change_attention_mode)
    add_filter.clicked.connect(add_attention_rule)
    remove_filter.clicked.connect(delete_attention_rule)
    refresh_rules()

    filters_layout.addWidget(QLabel("Prøv reglene med en lokal testmelding"))
    incoming_row = QHBoxLayout()
    sender_id = QLineEdit(filters)
    sender_id.setPlaceholderText("provider:stable-id")
    sender_id.setText("test:individuasjon-1")
    topic_label = QLineEdit(filters)
    topic_label.setPlaceholderText("Temaetikett (valgfri)")
    incoming_row.addWidget(sender_id)
    incoming_row.addWidget(topic_label)
    filters_layout.addLayout(incoming_row)
    verify_sender = QCheckBox("Identitet verifisert i denne lokale testen", filters)
    local_topic = QCheckBox("Tema klassifisert lokalt", filters)
    filters_layout.addWidget(verify_sender)
    filters_layout.addWidget(local_topic)
    incoming_body = QTextEdit(filters)
    incoming_body.setPlaceholderText("Testmelding – sendes ikke til noen")
    incoming_body.setMaximumHeight(65)
    filters_layout.addWidget(incoming_body)
    test_actions = QHBoxLayout()
    try_filter = QPushButton("Test beslutning (uten lagring)")
    add_sample = QPushButton("Legg lokal testmelding i filteret")
    test_actions.addWidget(try_filter)
    test_actions.addWidget(add_sample)
    filters_layout.addLayout(test_actions)
    decision_label = QLabel("")
    decision_label.setWordWrap(True)
    filters_layout.addWidget(decision_label)
    filtered_inbox = QListWidget(filters)
    filtered_inbox.setMaximumHeight(95)
    show_muted = QCheckBox("Vis også dempede", filters)
    filters_layout.addWidget(show_muted)
    filters_layout.addWidget(filtered_inbox)

    def incoming_args():
        return {
            "sender_id": sender_id.text(), "body": incoming_body.toPlainText(),
            "sender_verified": verify_sender.isChecked(),
            "topics": [topic_label.text()] if topic_label.text().strip() else [],
            "topics_trusted": local_topic.isChecked()
        }

    def refresh_filtered_inbox():
        prune(outbox)
        filtered_inbox.clear()
        for item in list_inbox(outbox, attention_owner,
                               include_muted=show_muted.isChecked()):
            filtered_inbox.addItem(
                item["state"].upper() + " · " + item["sender_display"] +
                " · " + item["body"][:60]
            )

    def simulate_decision():
        args = incoming_args()
        try:
            verdict = decide(outbox, attention_owner, **args)
            decision_label.setText(
                "Lokal test: " + verdict["decision"] + " (" +
                verdict["reason"] + "). Ingen sending og ingen mottakskvittering."
            )
        except ValueError as exc:
            decision_label.setText("Avvist: " + str(exc))

    def insert_local_sample():
        args = incoming_args()
        try:
            result = receive(
                outbox, attention_owner, source_id="local-test:" + uuid4().hex,
                channel="model", **args
            )
            decision_label.setText(
                "Lokal testmottak: " + result["decision"] +
                ". Ingen ekstern melding sendt eller mottatt."
            )
            refresh_filtered_inbox()
        except ValueError as exc:
            decision_label.setText("Avvist: " + str(exc))

    try_filter.clicked.connect(simulate_decision)
    add_sample.clicked.connect(insert_local_sample)
    show_muted.toggled.connect(refresh_filtered_inbox)
    refresh_filtered_inbox()
    tabs.addTab(filters, "Oppmerksomhet")

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
