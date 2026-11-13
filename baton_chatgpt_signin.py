"""OpenAI's documented Sign in with ChatGPT (SIWC) for local OSS apps.

The ChatGPT account authorizes inference via a separate OAuth grant; this
does not open the user's historical ChatGPT conversations. All secrets stay in
0600 local files and are never put in UI, process arguments or log output.
Use the system browser, loopback callback, PKCE S256 and validated OIDC ID JWT.
"""
import base64
from datetime import datetime, timezone
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import hmac
import json
import os
from pathlib import Path
import secrets
import socket
import stat
import tempfile
import time
from urllib.parse import parse_qs, urlencode, urlsplit
import urllib.error
import urllib.request
from uuid import uuid4
import webbrowser

AUTH_ROOT = "https://auth.openai.com"
AUTH_URL = AUTH_ROOT + "/api/accounts/authorize"
TOKEN_URL = AUTH_ROOT + "/api/accounts/oauth/token"
DISCOVERY = AUTH_ROOT + "/.well-known/openid-configuration"
RESOURCE = "https://api.openai.com/v1"
SCOPES = "openid profile email offline_access resource.invoke chatgpt.tokens.use.direct"
MAX_JSON = 1024 * 1024


def _config_dir():
    return Path.home() / ".config/baton"


def _secure_folder(path):
    path = Path(path)
    if path.is_symlink():
        raise ValueError("refusing linked credential directory")
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.is_symlink() or not path.is_dir():
        raise ValueError("invalid credential directory")
    if stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise PermissionError("credential directory is accessible to other users")
    return path


def _load_private(path):
    path = Path(path)
    if path.is_symlink():
        raise ValueError("refusing credential symlink")
    if not path.is_file():
        return None
    if stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise PermissionError("credentials must have 0600 permissions")
    if path.stat().st_size > MAX_JSON:
        raise ValueError("credential file too large")
    return json.loads(path.read_text(encoding="utf-8"))


def _save_private(path, data):
    path = Path(path)
    _secure_folder(path.parent)
    if path.is_symlink():
        raise ValueError("refusing credential symlink")
    old = _load_private(path)
    if old is not None and not isinstance(old, dict):
        raise ValueError("invalid credential record")
    fd, temporary = tempfile.mkstemp(prefix=".baton-oauth-", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def host_id(path=None):
    path = Path(path) if path else _config_dir() / "chatgpt-host.json"
    _secure_folder(path.parent)
    current = _load_private(path)
    if current is not None:
        value = current.get("ext_agent_host_id")
        if not isinstance(value, str) or not value.startswith("urn:uuid:"):
            raise ValueError("invalid registered host ID")
        return value
    value = "urn:uuid:" + str(uuid4())
    # Exclusive creation is required for identity stability on concurrent starts.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump({"ext_agent_host_id": value}, stream)
        stream.flush()
        os.fsync(stream.fileno())
    return value


def profile_path():
    return _config_dir() / "chatgpt-account.json"


def load_profile(path=None):
    profile = _load_private(path or profile_path())
    if profile is None:
        return None
    if not isinstance(profile, dict) or not isinstance(profile.get("client_id"), str):
        raise ValueError("invalid saved account")
    return profile


def _b64url(digest):
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def prepare_authorization(host, redirect, *, previous=None, state=None,
                          nonce=None, verifier=None):
    """Pure URI generation; no credentials are embedded in the browser URL."""
    state = state or secrets.token_urlsafe(32)
    nonce = nonce or secrets.token_urlsafe(32)
    verifier = verifier or secrets.token_urlsafe(48)
    if not redirect.startswith("http://127.0.0.1:") or not redirect.endswith("/auth/callback"):
        raise ValueError("OAuth callback must be a 127.0.0.1 loopback URL")
    if not host.startswith("urn:uuid:"):
        raise ValueError("invalid host ID")
    old_client = previous.get("client_id") if previous else None
    client = old_client or "dynamic_agent_client"
    values = {
        "client_id": client,
        "redirect_uri": redirect,
        "response_type": "code",
        "scope": SCOPES,
        "resource": RESOURCE,
        "state": state,
        "nonce": nonce,
        "code_challenge_method": "S256",
        "code_challenge": _b64url(hashlib.sha256(verifier.encode("ascii")).digest()),
        "ext_agent_host_id": host,
    }
    if not old_client:
        values["agent_name_hint"] = "Baton"
    elif previous.get("id_token"):
        values["id_token_hint"] = previous["id_token"]
    return {"url": AUTH_URL + "?" + urlencode(values),
            "state": state, "nonce": nonce, "verifier": verifier, "client_id": client}


def validate_callback(params, state, *, previous=None):
    """Check state/client ID before ANY token exchange."""
    if not isinstance(params, dict) or any(len(v) != 1 for v in params.values()):
        raise ValueError("ambiguous OAuth callback")
    received = params.get("state", [""])[0]
    if not hmac.compare_digest(received, state):
        raise ValueError("OAuth callback state mismatch")
    if "error" in params:
        raise PermissionError("ChatGPT sign-in was declined or cancelled")
    code = params.get("code", [""])[0]
    if not code or len(code) > 4096:
        raise ValueError("OAuth callback has no valid code")
    actual = params.get("client_id", [""])[0]
    if previous:
        expected = previous["client_id"]
        if actual and not hmac.compare_digest(actual, expected):
            raise ValueError("OAuth registered client mismatch")
        return code, expected
    if not actual or actual == "dynamic_agent_client" or len(actual) > 256:
        raise ValueError("missing issued OAuth client ID")
    return code, actual


def _https_json(url, *, form=None, bearer=None, timeout=20):
    if not url.startswith("https://") or urlsplit(url).username or urlsplit(url).password:
        raise ValueError("expected HTTPS URL")
    headers = {"Accept": "application/json"}
    if bearer:
        if "\r" in bearer or "\n" in bearer:
            raise ValueError("invalid bearer")
        headers["Authorization"] = "Bearer " + bearer
    data = None
    if form is not None:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        data = urlencode(form).encode("ascii")
    req = urllib.request.Request(url, data=data, headers=headers,
                                 method="POST" if form is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status != 200:
                raise RuntimeError("OpenAI returned unexpected HTTP status")
            raw = resp.read(MAX_JSON + 1)
    except urllib.error.HTTPError as e:
        raise RuntimeError("OpenAI HTTP " + str(e.code)) from None
    except urllib.error.URLError:
        raise RuntimeError("OpenAI connection failed") from None
    if len(raw) > MAX_JSON:
        raise RuntimeError("OpenAI reply too large")
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        raise RuntimeError("OpenAI response was not valid JSON") from None


def verify_id_token(id_token, client_id, nonce, *, discovery=None, key=None):
    """Require signed OIDC identity, NEVER trust a decoded-but-unverified JWT."""
    import jwt
    if discovery is None:
        discovery = _https_json(DISCOVERY)
    if discovery.get("issuer") != AUTH_ROOT:
        raise ValueError("OAuth issuer configuration mismatch")
    jwks_url = discovery.get("jwks_uri", "")
    if not isinstance(jwks_url, str) or not jwks_url.startswith(AUTH_ROOT + "/"):
        raise ValueError("unsafe OpenAI JWKS URL")
    signing_key = key if key is not None else jwt.PyJWKClient(jwks_url).get_signing_key_from_jwt(id_token).key
    claims = jwt.decode(
        id_token, signing_key, algorithms=["RS256"], audience=client_id,
        issuer=AUTH_ROOT,
        options={"require": ["sub", "iss", "aud", "exp", "iat", "nonce"]},
    )
    if not isinstance(claims["nonce"], str) or not hmac.compare_digest(claims["nonce"], nonce):
        raise ValueError("OpenAI identity nonce mismatch")
    if not isinstance(claims["sub"], str) or not claims["sub"]:
        raise ValueError("missing verified identity")
    return claims


def _exchange(code, client_id, verifier, redirect):
    return _https_json(TOKEN_URL, form={
        "grant_type": "authorization_code",
        "client_id": client_id,
        "code": code,
        "code_verifier": verifier,
        "redirect_uri": redirect,
        "resource": RESOURCE,
    })


def _profile_from_tokens(tokens, claims, client_id, host, previous=None):
    if not isinstance(tokens, dict) or tokens.get("token_type", "").lower() != "bearer":
        raise ValueError("invalid OAuth token response")
    for field in ("access_token", "id_token"):
        if not isinstance(tokens.get(field), str) or not tokens[field]:
            raise ValueError("missing OAuth " + field)
    if previous and previous.get("subject") != claims["sub"]:
        raise ValueError("ChatGPT account changed during reauthorization")
    scopes = tokens.get("scope", "").split()
    return {
        "client_id": client_id,
        "subject": claims["sub"],
        "email": claims.get("email", ""),
        "issuer": AUTH_ROOT,
        "ext_agent_host_id": host,
        "access_token": tokens["access_token"],
        "id_token": tokens["id_token"],
        "refresh_token": tokens.get("refresh_token"),
        "scopes": scopes,
        "saved_at": int(time.time()),
        "expires_at": int(time.time()) + int(tokens.get("expires_in", 3600)),
        "plan_enabled": "chatgpt.tokens.use.direct" in scopes,
    }


def sign_in(*, browser=None, storage=None, timeout=180):
    """User-initiated sign-in; run in a worker thread, never Qt UI thread."""
    if not 10 <= timeout <= 300:
        raise ValueError("invalid sign-in timeout")
    folder = _secure_folder(storage or _config_dir())
    host = host_id(folder / "chatgpt-host.json")
    path = folder / "chatgpt-account.json"
    previous = load_profile(path)
    data = {}
    class Callback(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urlsplit(self.path)
            if parsed.path != "/auth/callback" or parsed.fragment:
                self.send_error(404)
                return
            data["params"] = parse_qs(parsed.query, keep_blank_values=True)
            output = b"ChatGPT sign-in received. Return to Baton."
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Length", str(len(output)))
            self.end_headers()
            self.wfile.write(output)
        def log_message(self, *args):
            pass
    with HTTPServer(("127.0.0.1", 0), Callback) as server:
        server.timeout = 0.5
        callback = "http://127.0.0.1:" + str(server.server_port) + "/auth/callback"
        request = prepare_authorization(host, callback, previous=previous)
        opener = browser if browser is not None else webbrowser.open
        if not opener(request["url"]):
            raise RuntimeError("Could not open browser for ChatGPT sign-in")
        deadline = time.monotonic() + timeout
        while "params" not in data and time.monotonic() < deadline:
            server.handle_request()
        if "params" not in data:
            raise TimeoutError("ChatGPT sign-in timed out")
    code, issued_client = validate_callback(data["params"], request["state"], previous=previous)
    tokens = _exchange(code, issued_client, request["verifier"], callback)
    claims = verify_id_token(tokens["id_token"], issued_client, request["nonce"])
    profile = _profile_from_tokens(tokens, claims, issued_client, host, previous)
    _save_private(path, profile)
    return {"email": profile["email"], "subject": profile["subject"],
            "plan_enabled": profile["plan_enabled"]}


def access_token(*, storage=None):
    """Refresh the rotating token pair safely when it expires."""
    path = Path(storage) / "chatgpt-account.json" if storage else profile_path()
    profile = load_profile(path)
    if profile is None or not profile.get("plan_enabled"):
        raise PermissionError("Connect ChatGPT and approve plan usage first")
    if time.time() < profile["expires_at"] - 120:
        return profile["access_token"], profile
    refresh = profile.get("refresh_token")
    if not isinstance(refresh, str) or not refresh:
        raise PermissionError("ChatGPT session needs renewed sign-in")
    tokens = _https_json(TOKEN_URL, form={
        "grant_type": "refresh_token",
        "client_id": profile["client_id"],
        "refresh_token": refresh,
        "resource": RESOURCE,
    })
    scopes = tokens.get("scope", "").split()
    if "chatgpt.tokens.use.direct" not in scopes:
        raise PermissionError("ChatGPT plan permission is no longer granted")
    if not isinstance(tokens.get("refresh_token"), str) or not tokens["refresh_token"]:
        raise RuntimeError("OpenAI did not return a replacement refresh token")
    if not isinstance(tokens.get("access_token"), str) or not tokens["access_token"]:
        raise RuntimeError("OpenAI did not return a replacement access token")
    updated = dict(profile, access_token=tokens["access_token"],
                   refresh_token=tokens["refresh_token"], scopes=scopes,
                   saved_at=int(time.time()),
                   expires_at=int(time.time()) + int(tokens.get("expires_in", 3600)))
    _save_private(path, updated)
    return updated["access_token"], updated
