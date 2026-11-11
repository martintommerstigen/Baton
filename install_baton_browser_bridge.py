"""Install Baton's local browser Native Messaging host (no root, no secrets).

The Chrome/Brave unpacked extension requires ONE browser-side user approval.
The installer cannot secretly add extensions to an existing browser profile.
The pairing host uses the same Baton Core and local UI lease as the desktop
app, without a GitHub request or public network listener.
"""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import shlex
import stat
import tempfile


HOST_NAME = "com.baton.greg"
BROWSERS = (
    ".config/BraveSoftware/Brave-Browser/NativeMessagingHosts",
    ".config/google-chrome/NativeMessagingHosts",
    ".config/chromium/NativeMessagingHosts",
)
EXPECTED_EXTENSION_ID = "fdjgdjbdnoaidogmglbaaaffgodgaekk"


def _extension_id(root):
    manifest = root / "baton_extension/manifest.json"
    if not manifest.is_file() or manifest.is_symlink():
        raise ValueError("missing authentic Baton extension manifest")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    key = data.get("key")
    if not isinstance(key, str):
        raise ValueError("Baton extension identity missing")
    public = base64.b64decode(key,validate=True)
    digest = hashlib.sha256(public).digest()[:16]
    identity = "".join("abcdefghijklmnop"[n]
                       for byte in digest for n in (byte >> 4, byte & 15))
    if identity != EXPECTED_EXTENSION_ID:
        raise ValueError("Baton browser extension identity changed")
    return identity


def _atomic_private(path, text, *, mode):
    path = Path(path)
    parent = path.parent
    if parent.is_symlink():
        raise ValueError("destination directory is a symbolic link")
    parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    if path.is_symlink():
        raise ValueError("refusing linked file")
    fd, tmp = tempfile.mkstemp(prefix=".baton-install-",dir=parent)
    try:
        os.fchmod(fd,mode)
        with os.fdopen(fd,"w",encoding="utf-8") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def install_bridge(*, root=None, home=None, browsers=BROWSERS):
    if os.geteuid() == 0:
        raise PermissionError("Never install the Baton browser bridge as root")
    root = Path(root) if root is not None else Path(__file__).resolve().parent
    root = root.resolve(strict=True)
    home = Path(home) if home is not None else Path.home()
    script = root / "baton_browser_native_host.py"
    if not script.is_file() or script.is_symlink():
        raise ValueError("Baton Native Messaging host source missing")
    extension_id = _extension_id(root)
    origin = "chrome-extension://" + extension_id + "/"
    executable = home / ".local/bin/baton-browser-native-host"
    wrapper = ("#!/bin/sh\n"
               "export BATON_EXTENSION_ORIGIN=" + shlex.quote(origin) + "\n"
               "exec /usr/bin/python3 " + shlex.quote(str(script)) +
               ' "$@"\n')
    if executable.exists() and not executable.is_file():
        raise ValueError("unsafe native host launcher")
    if executable.is_file():
        existing = executable.read_text(encoding="utf-8")
        if existing != wrapper and "BATON_EXTENSION_ORIGIN=" not in existing:
            raise ValueError("refusing overwrite of unrelated native host launcher")
    _atomic_private(executable,wrapper,mode=0o700)
    host = {
        "name":HOST_NAME,
        "description":"Authenticated one-tab Baton Core connection for existing ChatGPT",
        "path":str(executable),
        "type":"stdio",
        "allowed_origins":[origin]
    }
    for browser in browsers:
        path = home / browser / (HOST_NAME+".json")
        if path.exists() and not path.is_symlink():
            prior = json.loads(path.read_text(encoding="utf-8"))
            if prior.get("name") != HOST_NAME or prior.get("allowed_origins") != [origin]:
                raise ValueError("refusing overwrite of different native host registration")
        _atomic_private(path,json.dumps(host,indent=2)+"\n",mode=0o600)
    return {"extension_id":extension_id,
            "extension_directory":str(root/"baton_extension"),
            "host_launcher":str(executable),
            "registered_browsers":len(browsers)}


def main():
    parser = argparse.ArgumentParser(description="Install one Baton Native Messaging bridge")
    parser.add_argument("--report",action="store_true")
    args = parser.parse_args()
    try:
        info = install_bridge()
    except (OSError,ValueError,PermissionError) as exc:
        parser.error(str(exc))
    print(json.dumps(info,ensure_ascii=False,indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
