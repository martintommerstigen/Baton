"""Opt-in model-to-Core bridge inside Baton's embedded ChatGPT window.

Unlike a native ChatGPT tool this uses an explicit in-conversation protocol.
The user must activate it for an exact chat. All page reads are restricted to
assistant-labelled turns in that chat and request IDs cannot run twice.
"""
import json
import queue
import threading
from uuid import uuid4
from pathlib import Path
from baton_chatgpt_view import is_chatgpt_conversation_url
from baton_conversation_panel import chat_id_from_url
from baton_embedded_send import prepare_send_script, send_click_script
from baton_model_protocol import (
    parse_assistant_tool_call, tool_result_message, observe_assistant_script
)
from baton_core_client import execute_on_greg


def bootstrap_message(nonce, cwd):
    example={"request_id":"0123456789abcdef0123456789abcdef","tool":"greg_exec",
             "argv":["/usr/bin/hostname"],"cwd":cwd,"timeout":15}
    return (
        "Baton local tool session is enabled for this existing ChatGPT conversation. "
        "The human authorized user-level command execution on Greg through Baton Core. "
        "This is a text protocol intercepted by the Baton app, not a native ChatGPT tool. "
        "To use it, make your ENTIRE NEXT assistant reply exactly these three lines "
        "(use a NEW random 32-character lowercase hexadecimal request_id; no code fences):\n"
        "BATON_TOOL_V1 "+nonce+"\n"
        +json.dumps(example,separators=(",",":"))+"\n"
        "END_BATON_TOOL_V1\n"
        "Start by requesting /usr/bin/hostname, then wait for the tool result. "
        "Do not claim commands have run unless Baton returns a matching result."
    )


def attach_model_bridge(layout, view, page, parent):
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QGroupBox, QVBoxLayout, QPushButton, QLabel
    group=QGroupBox("Baton · ChatGPT ⇄ Greg Core",parent)
    content=QVBoxLayout(group)
    description=QLabel("Modellen kan be om lokale kommandoer i denne samtalen. "
                       "Full brukertilgang på Greg. Aktiver eksplisitt.")
    description.setWordWrap(True)
    start=QPushButton("Aktiver modellverktøy i åpen samtale")
    stop=QPushButton("Stopp verktøyøkt")
    stop.setEnabled(False)
    state=QLabel("Ikke aktivert")
    state.setWordWrap(True)
    content.addWidget(description)
    content.addWidget(start)
    content.addWidget(stop)
    content.addWidget(state)
    layout.addWidget(group)

    session=[None]
    pending=[False]
    processed=set()
    results=queue.Queue()
    observer=QTimer(group)
    observer.setInterval(2000)
    output_poller=QTimer(group)
    output_poller.setInterval(350)

    def report(text):
        state.setText(text)

    def active():
        data=session[0]
        if data is None:
            return None
        if not is_chatgpt_conversation_url(view.url().toString(),data["chat_id"]):
            report("Verktøyøkten stoppet: samtalen ble endret.")
            disable()
            return None
        return data

    def disable():
        session[0]=None
        observer.stop()
        output_poller.stop()
        start.setEnabled(True)
        stop.setEnabled(False)
        pending[0]=False

    def transmit(text, on_complete):
        try:
            script=prepare_send_script(text)
        except ValueError:
            report("Meldingen er for lang for ChatGPT-feltet.")
            on_complete(False)
            return
        def prepared(result):
            if not isinstance(result,dict) or not result.get("ok"):
                report("Baton kunne ikke fylle ChatGPT-feltet: "+
                       (str(result.get("reason")) if isinstance(result,dict) else "ukjent"))
                on_complete(False)
                return
            if active() is None:
                on_complete(False)
                return
            def clicked(result):
                success=isinstance(result,dict) and bool(result.get("ok"))
                if not success:
                    report("ChatGPT-sendeknappen var ikke klar.")
                on_complete(success)
            page.runJavaScript(send_click_script(),clicked)
        page.runJavaScript(script,prepared)

    def begin():
        chat_id=chat_id_from_url(view.url().toString())
        if chat_id is None:
            report("Velg en eksisterende samtale fra ChatGPT-listen først.")
            return
        nonce=uuid4().hex
        session[0]={"chat_id":chat_id,"nonce":nonce}
        processed.clear()
        pending[0]=True
        start.setEnabled(False)
        stop.setEnabled(True)
        report("Starter økt i "+chat_id+" ...")
        cwd=str(Path.home())
        def booted(sent):
            pending[0]=False
            if not sent:
                report("Oppstartsmeldingen ble ikke sendt. Økten er stoppet.")
                disable()
                return
            report("Oppstartsmeldingen ble forsøkt sendt. Venter på modellens verktøyforespørsel ...")
            observer.start()
            output_poller.start()
        transmit(bootstrap_message(nonce,cwd),booted)

    def inspect():
        data=active()
        if data is None or pending[0]:
            return
        nonce=data["nonce"]
        def inspected(turns):
            if active() is None or pending[0] or not isinstance(turns,list):
                return
            for turn in turns:
                if not isinstance(turn,dict):
                    continue
                call=parse_assistant_tool_call(turn.get("text"),nonce)
                if call is None:
                    continue
                request_id=call["request_id"]
                if request_id in processed:
                    continue
                processed.add(request_id)
                pending[0]=True
                report("Verktøykall "+request_id[:8]+" mottatt. Kjører på Greg ...")
                def perform(request, request_nonce, cid):
                    try:
                        outcome=execute_on_greg(request["argv"],request["cwd"],request["timeout"])
                    except (ValueError, OSError, PermissionError, RuntimeError) as exc:
                        outcome={"exit_code":None,"output":"Baton execution error: "+type(exc).__name__}
                    results.put((request_nonce,cid,request["request_id"],outcome))
                threading.Thread(target=perform,args=(call,nonce,data["chat_id"]),daemon=True).start()
                break
        page.runJavaScript(observe_assistant_script(),inspected)

    def flush():
        if results.empty():
            return
        result_nonce, chat_id, request_id, outcome=results.get_nowait()
        data=active()
        if data is None or data["nonce"]!=result_nonce or data["chat_id"]!=chat_id:
            pending[0]=False
            report("Kommandoen er kjørt, men samtalen ble endret: resultatet ble ikke sendt.")
            return
        report("Kommando fullført; returnerer resultat til ChatGPT ...")
        result_text=tool_result_message(result_nonce,request_id,outcome)
        def result_sent(sent):
            pending[0]=False
            if sent:
                report("Resultat forsøkt sendt til ChatGPT. Venter på neste verktøykall.")
            else:
                report("Resultat kunne ikke sendes. Ingen automatisk gjensending.")
        transmit(result_text,result_sent)

    start.clicked.connect(begin)
    stop.clicked.connect(lambda: (disable(),report("Verktøyøkten er stoppet.")))
    observer.timeout.connect(inspect)
    output_poller.timeout.connect(flush)
    group.baton_bridge={"start":start,"stop":stop,"state":state,"observer":observer}
    return group
