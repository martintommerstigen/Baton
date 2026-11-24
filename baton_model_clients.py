"""A provider-neutral OpenAI-compatible chat transport for Baton.

This is a real client for Ollama and API endpoints implementing /chat/completions.
No desktop login scraping, no implicit device permission, no token persistence.
The caller chooses the endpoint, model and request explicitly.
"""
import json
from urllib.parse import urlsplit
import urllib.request
import urllib.error


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def validate_endpoint(url):
    if not isinstance(url, str) or len(url) > 1000:
        raise ValueError("invalid endpoint")
    parsed = urlsplit(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("unsupported endpoint URL")
    if parsed.username or parsed.password or parsed.fragment or parsed.query:
        raise ValueError("endpoint URL cannot contain credentials/query/fragment")
    if not parsed.path.endswith("/chat/completions"):
        raise ValueError("expected OpenAI-compatible /chat/completions endpoint")
    if parsed.scheme == "http" and parsed.hostname not in ("localhost", "127.0.0.1", "::1"):
        raise ValueError("plain HTTP allowed only on loopback")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("invalid endpoint port") from exc
    if port is not None and not 1 <= port <= 65535:
        raise ValueError("invalid endpoint port")
    return parsed.geturl()


def chat_completion(url, model, prompt, *, bearer=None, timeout=45, opener=None):
    validate_endpoint(url)
    if not isinstance(model, str) or not model.strip() or len(model) > 180:
        raise ValueError("invalid model")
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 12000:
        raise ValueError("invalid prompt")
    if not isinstance(timeout, int) or not 1 <= timeout <= 90:
        raise ValueError("invalid timeout")
    if bearer is not None and (not isinstance(bearer, str) or
                               not bearer.strip() or "\n" in bearer or "\r" in bearer):
        raise ValueError("invalid bearer token")
    payload = json.dumps(
        {"model": model, "messages": [{"role": "user", "content": prompt}],
         "stream": False}, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if bearer:
        headers["Authorization"] = "Bearer " + bearer
    request = urllib.request.Request(url, data=payload, method="POST", headers=headers)
    sender = opener if opener is not None else urllib.request.build_opener(_NoRedirect)
    try:
        with sender.open(request, timeout=timeout) as response:
            if response.status != 200:
                raise RuntimeError("provider returned non-200 HTTP status")
            raw = response.read(1048577)
    except urllib.error.HTTPError as exc:
        raise RuntimeError("provider HTTP " + str(exc.code)) from None
    except urllib.error.URLError:
        raise RuntimeError("provider not reachable") from None
    if len(raw) > 1048576:
        raise RuntimeError("provider reply too large")
    try:
        document = json.loads(raw)
        content = document["choices"][0]["message"]["content"]
    except (ValueError, TypeError, KeyError, IndexError):
        raise RuntimeError("provider reply has invalid format") from None
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("provider reply does not contain usable text")
    return content[:50000]
