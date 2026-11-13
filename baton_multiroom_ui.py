"""Native read-only-ish Baton multiroom UI; creates LOCAL drafts, never sends."""
from pathlib import Path
from baton_multiroom_reference import Multiroom, CHANNELS


def build_multiroom_widget(parent=None, *, store=None):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (
        QComboBox,QDialog,QDialogButtonBox,QFormLayout,QHBoxLayout,QLabel,
        QLineEdit,QListWidget,QMessageBox,QPushButton,QTableWidget,QTableWidgetItem,
        QVBoxLayout,QWidget
    )
    model=store or Multiroom(
        Path.home()/".local/state/baton/council",
        Path.home()/".local/state/baton/continuity")
    model.init()
    root=QWidget(parent)
    root.setObjectName("baton-multiroom")
    col=QVBoxLayout(root)
    intro=QLabel("Baton · Samtalerom og kanaler")
    intro.setStyleSheet("font-size:18px;font-weight:600;")
    col.addWidget(intro)
    caution=QLabel(
        "Mange faglige diskusjoner kan organiseres parallelt. "
        "Bare samme skrive-ressurs trenger eksklusiv tur. "
        "Tråder og utkast er IKKE ChatGPT-kjøringer, sendekvitteringer "
        "eller eksterne fullmakter.")
    caution.setWordWrap(True)
    col.addWidget(caution)
    topics=QListWidget(root)
    topics.setObjectName("baton-multiroom-topics")
    col.addWidget(topics)
    actions=QHBoxLayout()
    refresh=QPushButton("Oppdater tråder")
    new=QPushButton("Ny faglig tråd")
    for btn in (refresh,new): actions.addWidget(btn)
    col.addLayout(actions)
    channels=QTableWidget(root)
    channels.setObjectName("baton-multiroom-channels")
    channels.setColumnCount(3)
    channels.setHorizontalHeaderLabels(["Kanal","Tilstand","Begrensning"])
    channels.setRowCount(len(CHANNELS))
    for i,(name,spec) in enumerate(CHANNELS.items()):
        for j,value in enumerate((name,spec["state"],spec["truth"])):
            cell=QTableWidgetItem(value)
            cell.setFlags(cell.flags() & ~Qt.ItemFlag.ItemIsEditable)
            channels.setItem(i,j,cell)
    channels.resizeColumnsToContents()
    col.addWidget(channels)
    draft=QPushButton("Lag eksternt kontaktforslag (ingen sending)")
    draft.setObjectName("baton-multiroom-external-proposal")
    col.addWidget(draft)
    status=QLabel("Ingen melding er sendt. Eksterne utganger krever egne rettigheter.")
    status.setObjectName("baton-multiroom-status")
    status.setWordWrap(True)
    col.addWidget(status)

    def load_topics():
        topics.clear()
        for item in model.forum.list_topics():
            topics.addItem(f"{item['title']}  [{item['id']}]  · {item['posts']} observerte innlegg")
        status.setText("Trådene er oppdatert. Dette er lokale referansetråder, ikke levende modellkjøringer.")

    def add_topic():
        modal=QDialog(root);modal.setWindowTitle("Opprett faglig tråd")
        form=QFormLayout(modal)
        tid=QLineEdit(modal);tid.setPlaceholderText("kort-id-uten-mellomrom")
        title=QLineEdit(modal);title.setPlaceholderText("Spørsmål som andre kan undersøke")
        form.addRow("Tråd-ID:",tid);form.addRow("Tema:",title)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|
                                 QDialogButtonBox.StandardButton.Cancel,parent=modal)
        buttons.accepted.connect(modal.accept);buttons.rejected.connect(modal.reject)
        form.addRow(buttons)
        if modal.exec()!=QDialog.DialogCode.Accepted:return
        try:
            model.topic(tid.text().strip(),title.text().strip())
            load_topics()
            status.setText("Tråden er opprettet lokalt. Ingen ChatGPT-samtale ble startet.")
        except (ValueError, OSError) as exc:
            QMessageBox.warning(root,"Kunne ikke opprette tråd",str(exc))

    def add_external_proposal():
        modal=QDialog(root);modal.setWindowTitle("Eksternt kontaktforslag (IKKE Send)")
        form=QFormLayout(modal)
        sid=QLineEdit(modal);sid.setPlaceholderText("unik-id")
        topic=QComboBox(modal)
        for item in model.forum.list_topics():
            if item["state"]=="open":topic.addItem(item["title"],item["id"])
        route=QComboBox(modal)
        for name,item in CHANNELS.items():
            if item["kind"]=="external":route.addItem(name,name)
        target=QLineEdit(modal);target.setPlaceholderText("Kjent og legitim mottaker")
        purpose=QLineEdit(modal);purpose.setPlaceholderText("Hvorfor foreslås kontakt?")
        for label,widget in (("Forslags-ID:",sid),("Tema:",topic),
                ("Kanal:",route),("Mottakerreferanse:",target),
                ("Formål:",purpose)):
            form.addRow(label,widget)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|
                                 QDialogButtonBox.StandardButton.Cancel,parent=modal)
        buttons.accepted.connect(modal.accept);buttons.rejected.connect(modal.reject)
        form.addRow(buttons)
        if modal.exec()!=QDialog.DialogCode.Accepted:return
        try:
            result=model.propose_external(suggestion_id=sid.text().strip(),
                    topic_id=topic.currentData(),channel=route.currentData(),
                    recipient_hint=target.text().strip(),
                    purpose=purpose.text().strip())
            status.setText("Utkast lagret: "+result["suggestion_id"]+
                ". Ingen fullmakt, ingen ekstern melding.")
        except (ValueError,OSError) as exc:
            QMessageBox.warning(root,"Kunne ikke lagre forslag",str(exc))

    refresh.clicked.connect(load_topics)
    new.clicked.connect(add_topic)
    draft.clicked.connect(add_external_proposal)
    load_topics()
    root.baton_multiroom_controls={
        "topics":topics,"channels":channels,"refresh":refresh,"new":new,
        "propose":draft,"status":status,"store":model
    }
    return root


def show_multiroom_dialog(window):
    from PySide6.QtWidgets import QDialog,QVBoxLayout
    dlg=getattr(window,"_baton_multiroom_dialog",None)
    if dlg is not None and dlg.isVisible():
        dlg.raise_();dlg.activateWindow();return dlg
    dlg=QDialog(window)
    dlg.setWindowTitle("Baton · Flerrom og eksterne kanaler")
    dlg.resize(1000,700)
    layout=QVBoxLayout(dlg)
    layout.addWidget(build_multiroom_widget(dlg))
    window._baton_multiroom_dialog=dlg
    dlg.show()
    return dlg
