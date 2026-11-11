#!/usr/bin/env python3
"""Baton desktop: single local app for Core, models and communication channels.

ChatGPT accounts connect directly through OpenAI's documented OAuth plan
usage. The official ChatGPT Linux desktop is optional. Other providers use
documented APIs/MCP, not scraped website sessions.
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
    # Expire retained message bodies even when the user leaves Baton open.
    retention_timer = QTimer(panel)
    retention_timer.setInterval(10 * 60 * 1000)
    retention_timer.timeout.connect(lambda: prune(outbox))
    retention_timer.start()
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
    # ChatGPT plan usage connects directly to Baton via OpenAI's documented
    # OAuth flow. The official desktop app is optional, not a dependency.
    from queue import Queue, Empty
    from threading import Thread
    from baton_chatgpt_signin import sign_in, load_profile
    from baton_chatgpt_inference import list_models as chatgpt_list_models, chat as chatgpt_chat
    auth_results = Queue()
    try:
        current_profile = load_profile()
        chatgpt_connected = [bool(current_profile and current_profile.get("plan_enabled"))]
        initial_identity = current_profile.get("email") if current_profile else None
    except (OSError, ValueError, PermissionError):
        chatgpt_connected = [False]
        initial_identity = None
    connect_chatgpt = QPushButton("Fortsett med ChatGPT")
    chat_status = QLabel(
        ("ChatGPT-konto tilkoblet: " + (initial_identity or "registrert"))
        if chatgpt_connected[0] else
        "Koble ChatGPT-kontoen direkte til Baton. Ingen separat skrivebordsapp kreves."
    )
    chat_status.setWordWrap(True)
    models_layout.addWidget(connect_chatgpt)
    models_layout.addWidget(chat_status)

    def start_chatgpt_signin():
        connect_chatgpt.setEnabled(False)
        chat_status.setText("Åpner OpenAIs sikre innlogging i systemnettleseren ...")
        def worker():
            try:
                connection = sign_in()
                auth_results.put(("connected", connection))
                if connection["plan_enabled"]:
                    auth_results.put(("models", chatgpt_list_models()))
            except (OSError, RuntimeError, ValueError, PermissionError, TimeoutError) as exc:
                # OpenAI bearer tokens/callback query strings are never echoed.
                auth_results.put(("error", type(exc).__name__))
            except Exception:
                auth_results.put(("error", "Uventet feil under innlogging"))
        Thread(target=worker, name="baton-chatgpt-oauth", daemon=True).start()

    connect_chatgpt.clicked.connect(start_chatgpt_signin)
    tabs.addTab(models, "Modeller")

    # Working model-neutral chat: local Ollama or a chosen HTTPS
    # OpenAI-compatible endpoint, without scraping website accounts.
    # This plain-text answer never becomes an executable Greg command.
    from baton_model_clients import chat_completion

    model_chat = QWidget(tabs)
    chat_layout = QVBoxLayout(model_chat)
    chat_layout.addWidget(QLabel("Samtale med tilkoblet modell"))
    backend = QComboBox(model_chat)
    backend.addItem("ChatGPT-konto (OAuth / abonnement)", "chatgpt")
    backend.addItem("Lokal modell eller API-endepunkt", "compatible")
    chat_layout.addWidget(backend)
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
    models_available = []
    chatgpt_history = []

    def backend_changed(_index):
        is_api = backend.currentData() == "compatible"
        endpoint.setVisible(is_api)
        api_secret.setVisible(is_api)
        model_id.setPlaceholderText(
            "Velg en ChatGPT-modell fra kontoen" if not is_api
            else "Modell-ID hos valgt leverandør"
        )
        if not is_api and not chatgpt_connected[0]:
            model_result.setText("Koble ChatGPT-kontoen i fanen Modeller først.")

    backend.currentIndexChanged.connect(backend_changed)
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
        use_chatgpt = backend.currentData() == "chatgpt"
        if use_chatgpt and not chatgpt_connected[0]:
            model_result.setText("Logg inn med ChatGPT i fanen Modeller først.")
            return
        endpoint_url, model_name = endpoint.text(), model_id.text()
        if not model_name.strip():
            model_result.setText("Velg eller skriv en modell-ID først.")
            return
        token = api_secret.text().strip() or None
        model_busy[0] = True
        send_to_model.setEnabled(False)
        model_result.setText("Venter på modellen ...")
        transcript.append("Du: " + question)
        model_prompt.clear()
        sent_history = list(chatgpt_history) + [{"role": "user", "content": question}]

        def perform():
            try:
                if use_chatgpt:
                    reply, _ = chatgpt_chat(model_name, sent_history)
                    model_results.put(("ok", reply, "chatgpt-siwc", model_name,
                                       sent_history))
                else:
                    reply = chat_completion(endpoint_url, model_name, question,
                                            bearer=token, timeout=45)
                    model_results.put(("ok", reply, endpoint_url, model_name, None))
            except (OSError, ValueError, RuntimeError, PermissionError) as exc:
                # Provider errors must not print OAuth tokens or API keys.
                model_results.put(("error", type(exc).__name__,
                                   "chatgpt-siwc" if use_chatgpt else endpoint_url,
                                   model_name, None))
        Thread(target=perform, name="baton-model-chat", daemon=True).start()

    def poll_model_results():
        try:
            status, payload, answered_endpoint, answered_model, sent_history = model_results.get_nowait()
        except Empty:
            return
        model_busy[0] = False
        send_to_model.setEnabled(True)
        if status == "ok":
            # OAuth proves the account authorizing inference, not that the
            # model is an independent person. Filter identity remains scoped
            # and unverified for model-specific allowlisting.
            from hashlib import sha256
            sender = "model-api:" + sha256(
                (answered_endpoint + "|" + answered_model).encode("utf-8")
            ).hexdigest()[:20]
            verdict = receive(
                outbox, attention_owner, source_id="model-reply:" + uuid4().hex,
                channel="model", sender_id=sender, sender_verified=False,
                body=payload, topics=(), topics_trusted=False,
                sender_display=answered_model
            )
            if verdict["decision"] == "pass":
                transcript.append("Modell: " + payload)
                if sent_history is not None:
                    chatgpt_history[:] = (sent_history + [
                        {"role":"assistant", "content": payload}])[-24:]
                model_result.setText("Modellsvar mottatt. Filteravsender: " + sender)
            else:
                model_result.setText(
                    "Modellsvar " + verdict["decision"] +
                    " av mottakerens filter (" + verdict["reason"] + "). "
                    "Ingen tekst lagt i samtalevisningen. Avsender: " + sender
                )
        else:
            model_result.setText("Modellforespørsel feilet: " + payload)

    def poll_auth_results():
        try:
            action, result = auth_results.get_nowait()
        except Empty:
            return
        if action == "connected":
            connect_chatgpt.setEnabled(True)
            chatgpt_connected[0] = result["plan_enabled"]
            if result["plan_enabled"]:
                chat_status.setText(
                    "ChatGPT tilkoblet: " + (result["email"] or "verifisert konto") +
                    ". Modellene hentes nå fra kontoen."
                )
                backend.setCurrentIndex(0)
                tabs.setCurrentWidget(model_chat)
            else:
                chat_status.setText(
                    "Innlogging fullført, men bruk av ChatGPT-abonnementet "
                    "ble ikke godkjent. Tillat dette i OpenAIs innloggingsflyt."
                )
        elif action == "models":
            models_available[:] = result
            if result:
                model_id.setText(result[0]["slug"])
                model_result.setText(
                    "ChatGPT-modeller tilgjengelige: " +
                    ", ".join(item["name"] for item in result[:8]) +
                    ". Valgt: " + result[0]["slug"]
                )
            else:
                model_result.setText(
                    "Konto tilkoblet, men ingen modeller ble listet. "
                    "Modelltilgang må bekreftes med en faktisk forespørsel."
                )
        elif action == "error":
            connect_chatgpt.setEnabled(True)
            chat_status.setText(
                "ChatGPT-tilkobling mislyktes: " + result +
                ". Tidligere konto og lokale filer er ikke overskrevet."
            )

    send_to_model.clicked.connect(send_model_prompt)
    model_poller = QTimer(panel)
    model_poller.setInterval(180)
    model_poller.timeout.connect(poll_model_results)
    model_poller.start()
    auth_poller = QTimer(panel)
    auth_poller.setInterval(180)
    auth_poller.timeout.connect(poll_auth_results)
    auth_poller.start()
    QTimer.singleShot(0, lambda: backend_changed(backend.currentIndex()))
    if chatgpt_connected[0]:
        def load_saved_models():
            try:
                auth_results.put(("models", chatgpt_list_models()))
            except Exception:
                auth_results.put(("error", "Kan ikke hente kontomodeller"))
        Thread(target=load_saved_models, name="baton-chatgpt-model-list",
               daemon=True).start()
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
    from baton_install_status import inspect_installation
    install_status = QLabel("Installasjonskontroll: ikke kjørt.")
    install_status.setWordWrap(True)
    device_layout.addWidget(install_status)

    def refresh_install_status():
        # Read only: do not print tokens, config values, browser sessions,
        # private message text, process argv or Git remote credentials.
        info = inspect_installation()
        install_status.setText(
            "Installert branch: " + str(info["branch"] or "ukjent") + "\n" +
            "Revisjon: " + str(info["revision"] or "ukjent") + "\n" +
            "Ren arbeidstre: " + str(info["clean_worktree"]) + "\n" +
            "Core-port åpen (ikke autentisert): " +
            str(info["core_port_open_unverified"]) + "\n" +
            "Core-tjeneste aktiv (ikke autentisert): " +
            str(info["core_service_active_unverified"]) + "\n" +
            "UI-lease: " + str(info["ui_lease_live"]) + "\n" +
            "Core-token har private filrettigheter: " +
            str(info["core_token_private_mode_only"]) + "\n" +
            "Codex MCP-registrering: " + info["codex_mcp_config_state"] + "\n" +
            "Baton KDE-snarvei: " +
            str(info["baton_desktop_entry_matches"]) + "\n" +
            "Offisiell ChatGPT-klient funnet: " +
            str(info["official_chatgpt_binary_present"]) + "\n" +
            "Faktisk wake av eksisterende chatter: ikke verifisert"
        )

    check_install = QPushButton("Kontroller lokal installasjon (skrivebeskyttet)")
    check_install.clicked.connect(refresh_install_status)
    device_layout.addWidget(check_install)
    QTimer.singleShot(600, refresh_install_status)
    stop = QPushButton("Stopp Baton og trekk tilbake ny verktøytilgang")
    stop.clicked.connect(panel.close)
    device_layout.addWidget(stop)
    device_layout.addStretch(1)
    tabs.addTab(device, "Enhet og tilgang")
    panel.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
