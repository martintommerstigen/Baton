"""ChatGPT plan usage on OpenAI's documented Responses API route.

This is distinct from ordinary OpenAI API-key billing and from ChatGPT web
session scraping. No historical chats or extra tools are exposed by OAuth.
"""
import json
import urllib.error
import urllib.request

from baton_chatgpt_signin import access_token

MODELS_URL = "https://api.openai.com/v1/models"
RESPONSES_URL = "https://api.openai.com/v1/responses"
MAX_RESULT = 50000
MAX_SSE_BYTES = 4 * 1024 * 1024


def _request(url, token, *, data=None):
    if not isinstance(token, str) or not token or "\n" in token or "\r" in token:
        raise ValueError("invalid OAuth access token")
    headers = {"Authorization": "Bearer " + token, "Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    return urllib.request.Request(url, data=data, headers=headers,
                                  method="POST" if data is not None else "GET")


def _read_model_list(token, *, urlopen=None):
    send = urlopen if urlopen is not None else urllib.request.urlopen
    try:
        with send(_request(MODELS_URL, token), timeout=20) as response:
            if response.status != 200:
                raise RuntimeError("ChatGPT model list returned non-200")
            raw = response.read(1024 * 1024 + 1)
    except urllib.error.HTTPError as exc:
        raise RuntimeError("ChatGPT model list HTTP " + str(exc.code)) from None
    except urllib.error.URLError:
        raise RuntimeError("ChatGPT model list unavailable") from None
    if len(raw) > 1024 * 1024:
        raise RuntimeError("model list too large")
    try:
        models = json.loads(raw)["models"]
    except (ValueError, TypeError, KeyError):
        raise RuntimeError("invalid ChatGPT model list") from None
    if not isinstance(models, list):
        raise RuntimeError("invalid ChatGPT model list shape")
    result = []
    for item in models:
        if (isinstance(item, dict) and item.get("visibility") == "list"
                and isinstance(item.get("slug"), str)
                and isinstance(item.get("display_name"), str)):
            result.append({"slug": item["slug"], "name": item["display_name"]})
    return result[:100]


def list_models(*, storage=None):
    token, _ = access_token(storage=storage)
    return _read_model_list(token)


def _response_text(token, model, history, *, urlopen=None):
    if not isinstance(model, str) or not model.strip() or len(model) > 160:
        raise ValueError("model is required")
    if not isinstance(history, list) or not 1 <= len(history) <= 40:
        raise ValueError("invalid conversation history")
    prepared = []
    total = 0
    for item in history:
        if not isinstance(item, dict) or item.get("role") not in ("user", "assistant"):
            raise ValueError("invalid conversation role")
        content = item.get("content")
        if not isinstance(content, str) or not content.strip() or len(content) > 12000:
            raise ValueError("invalid conversation message")
        total += len(content)
        prepared.append({"role": item["role"], "content": content})
    if total > 35000:
        raise ValueError("conversation is too long; begin a new session")
    payload = json.dumps({"model": model, "input": prepared,
                          "store": False, "stream": True},
                         ensure_ascii=False).encode("utf-8")
    send = urlopen if urlopen is not None else urllib.request.urlopen
    chunks = []
    complete = False
    total_bytes = 0
    try:
        with send(_request(RESPONSES_URL, token, data=payload), timeout=120) as response:
            if response.status != 200:
                raise RuntimeError("ChatGPT inference returned non-200")
            for line in response:
                total_bytes += len(line)
                if total_bytes > MAX_SSE_BYTES:
                    raise RuntimeError("ChatGPT stream too large")
                if not line.startswith(b"data:"):
                    continue
                data = line[5:].strip()
                if data == b"[DONE]":
                    break
                try:
                    event = json.loads(data)
                except (UnicodeError, ValueError):
                    raise RuntimeError("invalid ChatGPT stream event") from None
                if not isinstance(event, dict):
                    raise RuntimeError("invalid ChatGPT stream type")
                kind = event.get("type")
                if kind == "response.output_text.delta":
                    delta = event.get("delta")
                    if isinstance(delta, str):
                        chunks.append(delta)
                        if sum(map(len, chunks)) > MAX_RESULT:
                            raise RuntimeError("ChatGPT response too long")
                elif kind in ("response.failed", "response.incomplete", "error"):
                    raise RuntimeError("ChatGPT response was not completed")
                elif kind == "response.completed":
                    completed = event.get("response", {})
                    if not isinstance(completed, dict) or completed.get("status") != "completed":
                        raise RuntimeError("ChatGPT response did not complete successfully")
                    complete = True
    except urllib.error.HTTPError as exc:
        raise RuntimeError("ChatGPT inference HTTP " + str(exc.code)) from None
    except urllib.error.URLError:
        raise RuntimeError("ChatGPT inference connection failed") from None
    if not complete:
        raise RuntimeError("ChatGPT stream ended without completion")
    result = "".join(chunks)
    if not result.strip():
        raise RuntimeError("ChatGPT response contained no text")
    return result


def chat(model, history, *, storage=None):
    token, profile = access_token(storage=storage)
    result = _response_text(token, model, history)
    # The subject is verified by OIDC during initial sign-in; it is a
    # provider-scoped identity, not the name of a permanent model person.
    return result, "openai:" + profile["subject"]
