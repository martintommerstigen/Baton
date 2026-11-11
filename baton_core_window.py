#!/usr/bin/env python3
"""Small Baton Core window for native ChatGPT MCP tools, no web DOM transport.

Keep this window open to authorize Greg user-level tool calls from a locally
configured ChatGPT desktop/Codex MCP host.
"""
import sys


def main():
    from PySide6.QtWidgets import (
        QApplication, QWidget, QVBoxLayout, QLabel, QPushButton
    )
    from baton_local_runtime import start_local_core, stop_local_core
    from baton_desktop_lease import create_ui_lease, release_ui_lease

    app = QApplication(sys.argv)
    core = start_local_core()
    try:
        lease = create_ui_lease()
    except Exception:
        stop_local_core(core)
        raise

    def shutdown():
        # Revoke the model's ability to request NEW commands before closing
        # the native Core listener (an in-flight command may still finish).
        release_ui_lease(lease)
        stop_local_core(core)

    app.aboutToQuit.connect(shutdown)
    panel = QWidget()
    panel.setWindowTitle("Baton · Greg MCP Core")
    layout = QVBoxLayout(panel)
    title = QLabel("Baton Core aktiv på Greg")
    title.setStyleSheet("font-size: 18px; font-weight: 600;")
    layout.addWidget(title)
    status = QLabel(
        "ChatGPT Linux Desktop / Codex MCP: klar\n"
        "Transport: lokal STDIO → autentisert Core (127.0.0.1:52526)\n"
        "Rettigheter: innlogget Linux-bruker, aldri root\n"
        "Ingen BATON_TOOL_V2-meldinger er nødvendige."
    )
    status.setWordWrap(True)
    layout.addWidget(status)
    risk = QLabel(
        "Dette gir modellen mulighet til å skrive og kjøre programmer som "
        "din Linux-bruker. Bruk bare betrodde samtaler og behold sikkerhetskopier."
    )
    risk.setWordWrap(True)
    layout.addWidget(risk)
    stop = QPushButton("Stopp Baton-verktøytilgang")
    stop.clicked.connect(panel.close)
    layout.addWidget(stop)
    panel.resize(490, 200)
    panel.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
