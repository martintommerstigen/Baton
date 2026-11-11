"""Persistent per-conversation model routing for the single Baton Core.

The registry stores conversation metadata, never API keys or model outputs.
Each message is explicitly routed to a local Ollama endpoint or OpenAI API.
No tool execution is inferred from model text.
"""
import json
import os
from pathlib import Path
import sqlite3
from baton_model_clients import chat_completion

LOCAL_URL = "http://127.0.0.1:11434/v1/chat/completions"
OPENAI_URL = "https://api.openai.com/v1/chat/completions"
BACKENDS = {"local": LOCAL_URL, "openai": OPENAI_URL}


def connect(path):
    path = Path(path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    db = sqlite3.connect(path)
    db.execute("""CREATE TABLE IF NOT EXISTS sessions (
        session_id TEXT PRIMARY KEY,
        backend TEXT NOT NULL,
        model TEXT NOT NULL,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""")
    return db


def select_model(db, session_id, backend, model):
    if not isinstance(session_id, str) or not (1 <= len(session_id) <= 128):
        raise ValueError("invalid session")
    if backend not in BACKENDS:
        raise ValueError("unsupported backend")
    if not isinstance(model, str) or not (1 <= len(model.strip()) <= 180):
        raise ValueError("invalid model")
    with db:
        db.execute("""INSERT INTO sessions(session_id, backend, model)
            VALUES (?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
            backend=excluded.backend, model=excluded.model,
            updated_at=CURRENT_TIMESTAMP""", (session_id, backend, model))


def route_message(db, session_id, prompt, *, api_key=None, sender=None):
    row = db.execute(
        "SELECT backend, model FROM sessions WHERE session_id=?", (session_id,)
    ).fetchone()
    if row is None:
        raise ValueError("unknown session")
    backend, model = row
    key = api_key if api_key is not None else os.environ.get("OPENAI_API_KEY")
    if backend == "openai" and not key:
        raise ValueError("OpenAI API key required")
    url = BACKENDS[backend]
    send = sender if sender is not None else chat_completion
    return send(url, model, prompt, bearer=key if backend == "openai" else None)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Baton single-Core dual-model session client")
    parser.add_argument("--db", default="~/.local/state/baton/model_sessions.sqlite")
    sub = parser.add_subparsers(dest="action", required=True)
    select = sub.add_parser("select")
    select.add_argument("session")
    select.add_argument("backend", choices=sorted(BACKENDS))
    select.add_argument("model")
    chat = sub.add_parser("chat")
    chat.add_argument("session")
    chat.add_argument("prompt")
    args = parser.parse_args()
    db = connect(args.db)
    try:
        if args.action == "select":
            select_model(db, args.session, args.backend, args.model)
            print("model selected")
        else:
            print(route_message(db, args.session, args.prompt))
    finally:
        db.close()


if __name__ == "__main__":
    main()
