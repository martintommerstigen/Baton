#!/usr/bin/env python3
"""Baton desktop v0.1: local-first GUI for the authenticated relay.
Python stdlib only. This client does not execute received commands.
"""
import json
import os
import threading
import tkinter as tk
import urllib.error
import urllib.request
from tkinter import messagebox, ttk

class BatonClient:
    def __init__(self, url, token):
        if not url.startswith(("http://127.0.0.1:", "http://localhost:", "https://")):
            raise ValueError("Remote Baton endpoints require HTTPS")
        self.url = url.rstrip("/")
        self.token = token

    def request(self, path, payload=None):
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self.url + path, data=data,
            headers={"Authorization": "Bearer " + self.token, "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=8) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            raise RuntimeError(f"HTTP {error.code}: {error.read(300).decode('utf-8', 'replace')}") from error

    def inbox(self):
        return self.request("/v1/inbox")["messages"]

    def send(self, recipient, body):
        return self.request("/v1/send", {"to": recipient, "body": body})

    def acknowledge(self, message_id):
        return self.request("/v1/ack", {"id": message_id})


class Desktop(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Baton Desktop — local-first")
        self.geometry("820x620")
        self.client = None
        self.messages = {}
        self.busy = False
        self.server = tk.StringVar(value=os.environ.get("BATON_URL", "http://127.0.0.1:8765"))
        self.identity = tk.StringVar(value=os.environ.get("BATON_IDENTITY", ""))
        self.token = tk.StringVar(value=os.environ.get("BATON_TOKEN", ""))
        self.recipient = tk.StringVar()
        self.status = tk.StringVar(value="Not connected")
        top = ttk.Frame(self, padding=12)
        top.pack(fill="x")
        for row, (label, variable, secret) in enumerate((
            ("Server", self.server, False), ("Identity (display only)", self.identity, False),
            ("Access token", self.token, True), ("Send to", self.recipient, False)
        )):
            ttk.Label(top, text=label).grid(row=row, column=0, sticky="w", pady=3)
            ttk.Entry(top, textvariable=variable, show="*" if secret else "").grid(row=row, column=1, sticky="ew", padx=8)
        top.columnconfigure(1, weight=1)
        ttk.Button(top, text="Connect / refresh", command=self.connect).grid(row=4, column=0, pady=8)
        ttk.Button(top, text="Send message", command=self.send).grid(row=4, column=1, sticky="w")
        ttk.Label(top, textvariable=self.status).grid(row=5, column=0, columnspan=2, sticky="w")
        ttk.Label(self, text="Compose message (text only)").pack(anchor="w", padx=12)
        self.compose = tk.Text(self, height=5, wrap="word")
        self.compose.pack(fill="x", padx=12, pady=4)
        ttk.Label(self, text="Inbox — select a message to acknowledge after reading").pack(anchor="w", padx=12)
        self.inbox_list = tk.Listbox(self, height=7)
        self.inbox_list.pack(fill="both", expand=True, padx=12, pady=4)
        self.inbox_list.bind("<<ListboxSelect>>", self.show_selected)
        self.details = tk.Text(self, height=6, state="disabled", wrap="word")
        self.details.pack(fill="both", expand=True, padx=12)
        ttk.Button(self, text="Acknowledge selected message", command=self.ack).pack(anchor="w", padx=12, pady=8)

    def work(self, operation, done):
        if self.busy:
            return
        self.busy = True
        self.status.set("Working…")
        def run():
            try:
                result = operation()
                self.after(0, lambda: finish(result, None))
            except Exception as exc:
                self.after(0, lambda: finish(None, str(exc)))
        def finish(result, error):
            self.busy = False
            if error:
                self.status.set("Error: " + error)
            else:
                done(result)
        threading.Thread(target=run, daemon=True).start()

    def connect(self):
        try:
            self.client = BatonClient(self.server.get().strip(), self.token.get().strip())
            if not self.token.get().strip():
                raise ValueError("Access token required")
        except ValueError as exc:
            self.status.set(str(exc))
            return
        self.refresh()

    def refresh(self):
        if not self.client:
            return
        def done(messages):
            self.messages = {m["id"]: m for m in messages}
            self.inbox_list.delete(0, "end")
            for mid, m in self.messages.items():
                self.inbox_list.insert("end", f"{mid}  |  {m['sender']}  |  {m['body'][:75]}")
            self.status.set(f"Connected; {len(messages)} unacknowledged message(s)")
        self.work(self.client.inbox, done)

    def send(self):
        if not self.client:
            self.status.set("Connect first")
            return
        target, body = self.recipient.get().strip(), self.compose.get("1.0", "end").strip()
        if not target or not body:
            self.status.set("Recipient and message required")
            return
        def done(result):
            self.status.set(f"Relay receipt: {result['status']} ({result['id']}); not recipient acknowledgement")
            self.compose.delete("1.0", "end")
        self.work(lambda: self.client.send(target, body), done)

    def show_selected(self, _event=None):
        selection = self.inbox_list.curselection()
        if not selection:
            return
        message = list(self.messages.values())[selection[0]]
        self.details.configure(state="normal")
        self.details.delete("1.0", "end")
        self.details.insert("end", json.dumps(message, ensure_ascii=False, indent=2))
        self.details.configure(state="disabled")

    def ack(self):
        if not self.client:
            return
        selection = self.inbox_list.curselection()
        if not selection:
            return
        mid = list(self.messages)[selection[0]]
        self.work(lambda: self.client.acknowledge(mid), lambda _result: self.refresh())

if __name__ == "__main__":
    Desktop().mainloop()