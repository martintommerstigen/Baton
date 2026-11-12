"""Native Baton HOWTO/FAQ UI backed by a local revisioned catalog.

This widget never visits, sends to, or changes ChatGPT / Core; changes to
published help require deliberate UI actions and cited sources.
Qt imports are lazy to keep headless Baton transports functional.
"""
from baton_help_catalog import HelpCatalog


def build_help_widget(parent=None, *, catalog=None):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (
        QApplication, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout,
        QLabel, QLineEdit, QListWidget, QMessageBox, QPushButton,
        QPlainTextEdit, QSplitter, QTabWidget, QTextBrowser, QVBoxLayout, QWidget
    )

    store = catalog or HelpCatalog()
    store.initialize()
    store.seed()

    root = QWidget(parent)
    root.setObjectName("baton-dynamic-help")
    vertical = QVBoxLayout(root)
    top = QLabel("Baton · HOWTO og FAQ")
    top.setStyleSheet("font-size: 19px; font-weight: 600;")
    vertical.addWidget(top)
    note = QLabel(
        "Søk i gjeldende råd. Rettelser og innvendinger kan foreslås av alle, "
        "men blir ikke gjeldende uten en eksplisitt lokal beslutning. "
        "Hjelpetekst gir aldri verktøytillatelse."
    )
    note.setWordWrap(True)
    vertical.addWidget(note)
    search = QLineEdit(root)
    search.setObjectName("baton-help-search")
    search.setPlaceholderText("Søk i HOWTO og FAQ")
    vertical.addWidget(search)
    categories = QTabWidget(root)
    categories.setObjectName("baton-help-tabs")
    vertical.addWidget(categories)
    lists = {}
    details = {}
    for kind, name in (("howto", "HOWTO"), ("faq", "FAQ")):
        pane = QWidget(categories)
        pane_layout = QVBoxLayout(pane)
        area = QSplitter(Qt.Orientation.Horizontal, pane)
        listbox = QListWidget(area)
        listbox.setObjectName("baton-help-list-"+kind)
        detail = QTextBrowser(area)
        detail.setObjectName("baton-help-detail-"+kind)
        detail.setOpenExternalLinks(False)  # no unsanctioned link/navigation
        detail.setPlainText("Velg en artikkel.")
        area.setSizes([260, 650])
        pane_layout.addWidget(area)
        lists[kind] = listbox
        details[kind] = detail
        categories.addTab(pane, name)

    actions = QHBoxLayout()
    refresh_btn = QPushButton("Oppdater")
    refresh_btn.setObjectName("baton-help-refresh")
    quickstart_btn = QPushButton("Kopier startkort for ny chat")
    quickstart_btn.setObjectName("baton-help-startcard")
    add_btn = QPushButton("Ny artikkel")
    add_btn.setObjectName("baton-help-new")
    proposal_btn = QPushButton("Foreslå rettelse")
    proposal_btn.setObjectName("baton-help-propose")
    apply_btn = QPushButton("Vurder forslag")
    apply_btn.setObjectName("baton-help-review")
    for button in (refresh_btn, quickstart_btn, add_btn, proposal_btn, apply_btn):
        actions.addWidget(button)
    vertical.addLayout(actions)
    status = QLabel("Hjelpen oppdateres fra lokal katalog.")
    status.setObjectName("baton-help-status")
    status.setWordWrap(True)
    vertical.addWidget(status)

    def kind():
        return ("howto","faq")[categories.currentIndex()]

    def selected_slug():
        item = lists[kind()].currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def selected():
        key = selected_slug()
        return store.get(key) if key else None

    def describe(item):
        label = {
            "current": "Gjeldende",
            "challenged": "Har åpne rettelsesforslag",
            "retired": "Pensjonert"
        }.get(item["status"], item["status"])
        parts = [
            item["title"],
            "",
            "Status: "+label+"  |  Revisjon: "+str(item["revision"]),
            "Kilde: "+item["source"],
            "Siste begrunnelse: "+item["reason"],
            "",
            item["body"],
            "",
            "Versjonshistorikk (nyeste først):"
        ]
        for history in item["history"]:
            parts.append(
                f"• rev. {history['revision']}: {history['title']} "
                f"— {history['source']} ({history['reason']})"
            )
        if item["proposals"]:
            parts.append("\nForslag / innvendinger (uaktiverte inntil eksplisitt valg):")
            for proposal in item["proposals"]:
                parts.append(
                    f"• #{proposal['id']} — {proposal['status']}, mot revisjon "
                    f"{proposal['base_revision']}: {proposal['reason']} "
                    f"[{proposal['source']}]"
                )
        return "\n".join(parts)

    def show_selected(current=None, previous=None):
        value = selected()
        details[kind()].setPlainText(describe(value) if value else "Velg en artikkel.")
        proposal_btn.setEnabled(bool(value))
        apply_btn.setEnabled(bool(value and any(
            p["status"]=="open" for p in value["proposals"])))

    def refresh():
        preserve = {name:
            (widgets.currentItem().data(Qt.ItemDataRole.UserRole)
             if widgets.currentItem() else None)
            for name, widgets in lists.items()}
        found = 0
        try:
            for typ, widgets in lists.items():
                widgets.blockSignals(True)
                widgets.clear()
                for article in store.list(typ, search.text()):
                    from PySide6.QtWidgets import QListWidgetItem
                    suffix = "  ⚑" if article["status"] == "challenged" else ""
                    line = QListWidgetItem(article["title"] + suffix)
                    line.setData(Qt.ItemDataRole.UserRole, article["slug"])
                    widgets.addItem(line)
                    found += 1
                for index in range(widgets.count()):
                    if widgets.item(index).data(Qt.ItemDataRole.UserRole)==preserve[typ]:
                        widgets.setCurrentRow(index)
                        break
                if widgets.currentRow()<0 and widgets.count():
                    widgets.setCurrentRow(0)
                widgets.blockSignals(False)
            show_selected()
            status.setText(f"{found} treff. Gjeldende artikler hentes fra lokal katalog.")
        except (ValueError, OSError) as exc:
            status.setText("Kan ikke oppdatere hjelpen: "+str(exc))

    def edit_dialog(title, original=None, creating=False):
        dialog = QDialog(root)
        dialog.setWindowTitle(title)
        dialog.resize(680,540)
        form = QFormLayout(dialog)
        slug = QLineEdit(dialog)
        slug.setText("" if creating else original["slug"])
        slug.setReadOnly(not creating)
        t = QLineEdit(dialog)
        t.setText("" if creating else original["title"])
        body = QPlainTextEdit(dialog)
        body.setPlainText("" if creating else original["body"])
        body.setMinimumHeight(215)
        source = QLineEdit(dialog)
        source.setPlaceholderText("Kilde: melding-ID, test, dokument eller egen observasjon")
        reason = QLineEdit(dialog)
        reason.setPlaceholderText("Hva er nytt, feil eller avgrenset?")
        form.addRow("ID:", slug)
        form.addRow("Tittel:", t)
        form.addRow("Innhold:", body)
        form.addRow("Kilde:", source)
        form.addRow("Begrunnelse:", reason)
        buttons=QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel, parent=dialog)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec()!=QDialog.DialogCode.Accepted:
            return
        try:
            if creating:
                result=store.add(slug.text().strip(),kind(),t.text(),body.toPlainText(),
                                 source.text(),reason.text())
                status.setText("Opprettet "+result["slug"]+". Dette er lokal dokumentasjon, ikke en Core-endring.")
            else:
                pid=store.propose(original["slug"],original["revision"],t.text(),
                                  body.toPlainText(),source.text(),reason.text())
                status.setText(f"Rettelse #{pid} lagret. Ikke aktivert. Bruk «Vurder forslag».")
            refresh()
        except (OSError, ValueError) as exc:
            QMessageBox.warning(root, "Kan ikke lagre hjelpetekst", str(exc))

    def new_article():
        edit_dialog("Ny HOWTO-artikkel" if kind()=="howto" else "Nytt FAQ-spørsmål",
                    creating=True)

    def propose():
        row = selected()
        if row is not None:
            edit_dialog("Foreslå en kildebevart rettelse", row)

    def review():
        row = selected()
        if not row:
            return
        open_proposals = [p for p in row["proposals"] if p["status"]=="open"]
        if not open_proposals:
            status.setText("Ingen åpne forslag.")
            return
        dialog=QDialog(root)
        dialog.setWindowTitle("Vurder gjeldende råd og foreslått revisjon")
        dialog.resize(700,550)
        box=QVBoxLayout(dialog)
        chooser=QComboBox(dialog)
        for p in open_proposals:
            chooser.addItem(f"#{p['id']}: {p['reason']}", p["id"])
        preview=QPlainTextEdit(dialog)
        preview.setReadOnly(True)
        def update_preview():
            id_=chooser.currentData()
            p=next(v for v in open_proposals if v["id"]==id_)
            preview.setPlainText(
                f"GJELDENDE rev. {row['revision']}\n{row['body']}\n\n"
                f"FORESLÅTT fra {p['source']}\n{p['title']}\n{p['body']}\n\n"
                f"BEGRUNNELSE\n{p['reason']}\n\n"
                "Dette endrer bare lokal HELP-tekst. Ingen tillatelse eller sending.")
        chooser.currentIndexChanged.connect(update_preview)
        update_preview()
        box.addWidget(QLabel("Velg og kontroller hele endringen før du tar den i bruk:"))
        box.addWidget(chooser)
        box.addWidget(preview)
        buttons = QDialogButtonBox(dialog)
        accept=buttons.addButton("Ta i bruk eksplisitt",QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.addButton(QDialogButtonBox.StandardButton.Cancel)
        accept.clicked.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        box.addWidget(buttons)
        if dialog.exec()!=QDialog.DialogCode.Accepted:
            return
        if QMessageBox.question(
            root, "Aktiver revisjon?",
            f"Ta i bruk forslag #{chooser.currentData()} som ny versjon av «{row['title']}»?"
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            result=store.apply(chooser.currentData(),row["revision"])
            status.setText(
                "Hjelpeteksten er oppdatert til revisjon "+str(result["revision"])
                if result["applied"] else
                "Forslaget er foreldet. Gjennomgå den nyere revisjonen før en ny rettelse."
            )
            refresh()
        except (OSError, ValueError) as exc:
            QMessageBox.warning(root,"Kan ikke aktivere revisjon",str(exc))

    def copy_start_card():
        from baton_onboarding import peer_quickstart
        from baton_ui_pause import ui_writes_paused
        text = peer_quickstart(catalog=store, has_active_bridge=False,
                               paused=ui_writes_paused())
        QApplication.clipboard().setText(text)
        status.setText("Startkort kopiert. Ingen modellverktøy aktivert, ingen melding sendt.")

    refresh_btn.clicked.connect(refresh)
    quickstart_btn.clicked.connect(copy_start_card)
    add_btn.clicked.connect(new_article)
    proposal_btn.clicked.connect(propose)
    apply_btn.clicked.connect(review)
    search.textChanged.connect(lambda _:refresh())
    categories.currentChanged.connect(lambda _:show_selected())
    for widgets in lists.values():
        widgets.currentItemChanged.connect(show_selected)
    refresh()
    # Expose stable control names for UI regression tests and accessibility.
    root.baton_help_controls = {
        "search":search, "tabs":categories, "lists":lists,
        "details":details, "refresh":refresh_btn, "startcard":quickstart_btn, "new":add_btn,
        "propose":proposal_btn, "review":apply_btn, "status":status,
        "store":store
    }
    return root


def show_help_dialog(window, *, catalog=None):
    from PySide6.QtWidgets import QDialog, QVBoxLayout
    dialog=getattr(window,"_baton_help_dialog",None)
    if dialog is not None and dialog.isVisible():
        dialog.raise_()
        dialog.activateWindow()
        return dialog
    dialog=QDialog(window)
    dialog.setWindowTitle("Baton · Dynamisk HOWTO og FAQ")
    dialog.resize(910,710)
    layout=QVBoxLayout(dialog)
    layout.addWidget(build_help_widget(dialog,catalog=catalog))
    window._baton_help_dialog=dialog
    dialog.show()
    return dialog
