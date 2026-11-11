"""Baton's native messaging host for Brave/Chromium.

This host bridges exactly one manually authorized EXISTING ChatGPT tab to the
already-running local Baton Core. No GitHub transport, cloud token, cookie
extraction, shell interpolation, or background automatic wake.

Native messaging caller origin MUST match the registered extension ID.
The browser's content-script UI must show explicit activate/stop controls.
"""
import json
import os
from pathlib import Path
import re
import secrets
import struct
import sys
import time

from baton_core_client import execute_on_greg
from baton_desktop_lease import ui_lease_active
from baton_model_protocol import parse_assistant_tool_call, tool_result_message

CHAT_ID = re.compile(r"[0-9a-f]{8}-[0-9a-f-]{20,64}\Z", re.I)
MAX_NATIVE_MESSAGE = 64 * 1024
MAX_SESSION_SECONDS = 3600


class NativeHostSession:
    def __init__(self, *, client=None, lease=None, clock=None):
        self.client = client or execute_on_greg
        self.lease = lease or ui_lease_active
        self.clock = clock or time.monotonic
        self.chat_id = None
        self.nonce = None
        self.expires = 0
        self.used = set()

    def _active(self, chat_id=None):
        return (self.nonce is not None and self.chat_id is not None
                and self.clock() < self.expires and self.lease()
                and (chat_id is None or self.chat_id == chat_id))

    def handle(self, request):
        if not isinstance(request, dict):
            return {"ok":False,"error":"invalid-message"}
        op = request.get("op")
        if op == "arm":
            if set(request) != {"op","chat_id"}:
                return {"ok":False,"error":"invalid-arm-shape"}
            chat = request["chat_id"]
            if not isinstance(chat,str) or not CHAT_ID.fullmatch(chat):
                return {"ok":False,"error":"invalid-chat-id"}
            if not self.lease():
                return {"ok":False,"error":"baton-ui-not-running"}
            # One live tab per process. A second selection replaces prior
            # authority, and old nonces cannot be reused.
            self.chat_id = chat
            self.nonce = secrets.token_hex(16)
            self.expires = self.clock() + MAX_SESSION_SECONDS
            self.used.clear()
            return {"ok":True,"op":"armed","chat_id":chat,"nonce":self.nonce,
                    "expires_in":MAX_SESSION_SECONDS}
        if op == "stop":
            self.chat_id = None
            self.nonce = None
            self.expires = 0
            self.used.clear()
            return {"ok":True,"op":"stopped"}
        if op == "status":
            return {"ok":True,"op":"status","active":self._active()}
        if op != "execute_frame" or set(request) != {"op","chat_id","frame"}:
            return {"ok":False,"error":"unsupported-command"}
        chat = request.get("chat_id")
        frame = request.get("frame")
        if not self._active(chat):
            return {"ok":False,"error":"session-inactive-or-chat-mismatch"}
        parsed = parse_assistant_tool_call(frame, self.nonce)
        if parsed is None:
            return {"ok":False,"error":"invalid-or-unauthorized-tool-frame"}
        request_id = parsed["request_id"]
        if request_id in self.used:
            return {"ok":False,"error":"duplicate-request"}
        # Reserve before execution: uncertain results may never be resent
        # automatically, even when the first execution timed out.
        self.used.add(request_id)
        try:
            result = self.client(parsed["argv"], parsed["cwd"], parsed["timeout"])
            if not isinstance(result, dict):
                raise RuntimeError("invalid Core reply")
            response = tool_result_message(self.nonce, request_id, result)
        except (OSError, PermissionError, ValueError, TypeError, RuntimeError):
            response = tool_result_message(self.nonce, request_id,
                {"exit_code":None,"output":"Baton Core command failed; delivery uncertain"})
        return {"ok":True,"op":"tool_result","chat_id":chat,
                "request_id":request_id,"frame":response}


def _read_packet(input_stream):
    header = input_stream.read(4)
    if not header:
        return None
    if len(header) != 4:
        raise ValueError("truncated-length")
    length = struct.unpack("<I", header)[0]
    if not 1 <= length <= MAX_NATIVE_MESSAGE:
        raise ValueError("invalid-length")
    data = input_stream.read(length)
    if len(data) != length:
        raise ValueError("truncated-payload")
    value = json.loads(data.decode("utf-8"))
    if not isinstance(value,dict):
        raise ValueError("invalid-json-shape")
    return value


def _write_packet(output_stream, value):
    encoded = json.dumps(value,ensure_ascii=False,separators=(",",":")).encode("utf-8")
    if len(encoded) > MAX_NATIVE_MESSAGE:
        raise ValueError("outbound-packet-too-large")
    output_stream.write(struct.pack("<I",len(encoded)))
    output_stream.write(encoded)
    output_stream.flush()


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    expected = os.environ.get("BATON_EXTENSION_ORIGIN","")
    if os.geteuid() == 0:
        return 3
    # Chromium sends the calling extension's origin as argv[1] to the native
    # host. The installer fixes allowed_origins in the manifest as well.
    if len(args) < 1 or not expected or args[0] != expected:
        return 4
    host = NativeHostSession()
    while True:
        try:
            message = _read_packet(sys.stdin.buffer)
        except (ValueError,UnicodeError,OverflowError,json.JSONDecodeError):
            return 2
        if message is None:
            return 0
        try:
            reply = host.handle(message)
            _write_packet(sys.stdout.buffer,reply)
        except (OSError,ValueError,RuntimeError):
            return 2


if __name__ == "__main__":
    raise SystemExit(main())
