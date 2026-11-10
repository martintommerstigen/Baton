#!/usr/bin/env python3
"""Read-only local Baton diagnostics. Never reads tokens or sends messages."""
import argparse
import json
from pathlib import Path
import socket
import sys

def check(host="127.0.0.1", port=8765, root=None):
    if host not in ("127.0.0.1", "::1", "localhost"):
        raise ValueError("Only loopback hosts are permitted")
    root = Path(root) if root else Path(__file__).resolve().parents[1]
    result = {
        "repository_present": (root / "client.py").is_file() and (root / "server.py").is_file(),
        "loopback_listener": False,
        "authenticated": "not_checked",
        "chat_wake": "not_checked",
    }
    try:
        with socket.create_connection((host, port), timeout=0.5):
            result["loopback_listener"] = True
    except OSError:
        pass
    return result

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error("port out of range")
    print(json.dumps(check(port=args.port), indent=2))
    return 0

if __name__ == "__main__":
    sys.exit(main())
