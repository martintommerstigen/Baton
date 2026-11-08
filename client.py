#!/usr/bin/env python3
"""Baton CLI: authenticated text-only client, Python standard library.

Remote endpoints MUST use HTTPS. Acknowledgements are explicit; receiving
or printing a message never automatically acknowledges it.
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid


def validate_endpoint(endpoint):
    parsed = urllib.parse.urlsplit(endpoint)
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("Endpoint must not contain credentials, query or fragment")
    if parsed.scheme == "https" and parsed.hostname:
        return endpoint.rstrip("/")
    if parsed.scheme == "http" and parsed.hostname in ("localhost", "127.0.0.1", "::1"):
        return endpoint.rstrip("/")
    raise ValueError("Use HTTPS for remote endpoints; HTTP is only allowed on loopback")


class BatonCLI:
    def __init__(self, endpoint, token):
        self.endpoint = validate_endpoint(endpoint)
        if not token:
            raise ValueError("BATON_TOKEN is required")
        self.token = token

    def call(self, method, path, payload=None):
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self.endpoint + path,
            data=data,
            method=method,
            headers={
                "Authorization": "Bearer " + self.token,
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=12) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            raise RuntimeError(f"HTTP {error.code}: {error.read(256).decode('utf-8', 'replace')}") from None

    def inbox(self):
        return self.call("GET", "/v1/inbox")

    def send(self, recipient, body, message_id=None):
        return self.call(
            "POST",
            "/v1/send",
            {"id": message_id or str(uuid.uuid4()), "to": recipient, "body": body},
        )

    def ack(self, message_id):
        return self.call("POST", "/v1/ack", {"id": message_id})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=os.environ.get("BATON_URL", "http://127.0.0.1:8765"))
    parser.add_argument("--token-env", default="BATON_TOKEN", help="Environment variable holding the token")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("inbox", help="Read unacknowledged messages; does not ACK")
    send = commands.add_parser("send", help="Queue a text message")
    send.add_argument("--to", required=True)
    send.add_argument("--body", required=True)
    send.add_argument("--id", help="Stable ID for safe retries")
    ack = commands.add_parser("ack", help="Explicit client acknowledgement")
    ack.add_argument("--id", required=True)
    args = parser.parse_args(argv)
    try:
        client = BatonCLI(args.url, os.environ.get(args.token_env, ""))
        if args.command == "inbox":
            result = client.inbox()
        elif args.command == "send":
            result = client.send(args.to, args.body, args.id)
        else:
            result = client.ack(args.id)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, RuntimeError, urllib.error.URLError, TimeoutError) as error:
        print(f"Baton error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
