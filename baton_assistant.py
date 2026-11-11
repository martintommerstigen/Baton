"""A local assistant entrypoint using the existing Baton model router.

Commands are explicit; generated text is never executed as a shell command.
"""
import argparse
import os
from pathlib import Path
from baton_dual_model_sessions import connect, select_model, route_message

DEFAULT_DB = Path.home() / ".local/state/baton/model_sessions.sqlite"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Baton dual-model assistant")
    parser.add_argument("--db", default=str(DEFAULT_DB))
    sub = parser.add_subparsers(dest="command", required=True)
    setup = sub.add_parser("use", help="Select model for an existing or new session")
    setup.add_argument("session")
    setup.add_argument("provider", choices=["local", "openai"])
    setup.add_argument("model")
    ask = sub.add_parser("ask", help="Send text to the selected model")
    ask.add_argument("session")
    ask.add_argument("message")
    status = sub.add_parser("status", help="Show configured model, never secrets")
    status.add_argument("session")
    args = parser.parse_args(argv)
    db = connect(args.db)
    try:
        if args.command == "use":
            select_model(db, args.session, args.provider, args.model)
            print("Selected model for " + args.session)
        elif args.command == "status":
            row = db.execute(
                "SELECT backend, model FROM sessions WHERE session_id=?",
                (args.session,)
            ).fetchone()
            if row is None:
                parser.error("session not configured")
            print(row[0] + ": " + row[1])
        else:
            print(route_message(db, args.session, args.message))
    finally:
        db.close()


if __name__ == "__main__":
    main()
