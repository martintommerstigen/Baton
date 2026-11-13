"""Read-only audit: a narrow Baton proxy cannot enforce policy if raw CDP remains exposed.

This audit sends ONLY GET /json/version and GET /json/list to explicitly
specified LOOPBACK ports. It never connects to returned WebSockets, evaluates
JavaScript, navigates, sends messages, logs target URLs, or prints tokens.

Run: python3 baton_cdp_boundary_audit.py --port 9335 --port 9448
Treat 'raw_discovery_exposed' as a *bypass opportunity*, not proof of misuse.
"""
import argparse
import json
import urllib.request
from datetime import datetime, timezone


def _fetch(port, endpoint, *, timeout):
    # No request controlled URL, only fixed loopback plus fixed CDP paths.
    url = f"http://127.0.0.1:{port}{endpoint}"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    # Refuse HTTP redirects; the audit never needs them.
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, request, fp, code, msg, headers, newurl):
            return None
    opener = urllib.request.build_opener(NoRedirect)
    with opener.open(req, timeout=timeout) as response:
        if response.status != 200:
            raise RuntimeError("non-200 HTTP response")
        payload = response.read(131073)
        if len(payload) > 131072:
            raise ValueError("oversize CDP discovery response")
        return json.loads(payload)


def audit_port(port, *, timeout=1.0):
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError("port must be an integer 1..65535")
    result = {
        "port": port,
        "reachable": False,
        "raw_discovery_exposed": False,
        "browser_websocket_disclosed": False,
        "page_websocket_disclosed": False,
        "page_count": None,
        "status": "unavailable_or_undetermined",
    }
    try:
        v = _fetch(port, "/json/version", timeout=timeout)
        result["reachable"] = True
        result["browser_websocket_disclosed"] = (
            isinstance(v, dict) and
            isinstance(v.get("webSocketDebuggerUrl"), str) and
            v["webSocketDebuggerUrl"].startswith("ws://")
        )
        pages = _fetch(port, "/json/list", timeout=timeout)
        if not isinstance(pages, list):
            raise ValueError("invalid CDP target list")
        result["page_count"] = sum(
            p.get("type") == "page" for p in pages if isinstance(p, dict)
        )
        result["page_websocket_disclosed"] = any(
            p.get("type") == "page"
            and isinstance(p.get("webSocketDebuggerUrl"), str)
            and p["webSocketDebuggerUrl"].startswith("ws://")
            for p in pages if isinstance(p, dict)
        )
        result["raw_discovery_exposed"] = (
            result["browser_websocket_disclosed"] or
            result["page_websocket_disclosed"]
        )
        result["status"] = ("raw_cdp_bypass_opportunity" if
                            result["raw_discovery_exposed"] else
                            "endpoint_reachable_no_websocket_disclosed")
    except Exception as exc:
        # No URLs, user data, session tokens or raw exception message in output.
        result["status"] = "discovery_failed_" + type(exc).__name__
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, action="append", required=True)
    args = parser.parse_args()
    print(json.dumps({
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "capability_claim": "no-CDP-commands-executed",
        "results": [audit_port(p) for p in args.port],
    }, indent=2))


if __name__ == "__main__":
    main()
