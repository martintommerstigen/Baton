"""Negative contract: local KDE socket must not imply model send authority.

Targets the ACTUAL perform()/received() definitions of the inspected pilot,
compiled in an isolated namespace. The real module MUST NOT be imported:
it would initialize KDE D-Bus and could request a live portal session.
All sockets, keyboard effects and focus changes below are fakes.
"""
import ast
import json
import os
from pathlib import Path
import socket
import struct
import types
import unittest

SOURCE = Path(os.environ.get(
    "BATON_KDE_CONTROLLER_SOURCE",
    "/home/olliver/.local/share/baton-som-links-20261113/ops/baton_kde_desktop_controller.py"
))


class FakeConnection:
    def __init__(self, command, observed_uid, desktop, switch_focus=None):
        self.command = command
        self.observed_uid = observed_uid
        self.desktop = desktop
        self.switch_focus = switch_focus
        self.responses = []
        self.closed = False

    def settimeout(self, n):
        pass

    def getsockopt(self, level, option, size):
        # Linux supplies this UID in reality. The fake only models the
        # authenticated SAME-UID client the genuine source already trusts.
        if self.switch_focus:
            self.desktop["focus"] = self.switch_focus
        return struct.pack("3i", 100, self.observed_uid, 100)

    def recv(self, n):
        return json.dumps(self.command).encode()

    def sendall(self, body):
        self.responses.append(json.loads(body))

    def close(self):
        self.closed = True


class FakeListener:
    def __init__(self, connection):
        self.connection = connection

    def accept(self):
        return self.connection, None


def isolated_controller(command, *, uid=None, initial_focus="gemini",
                        focus_after_peer_check=None):
    """Run real parsed handlers with fake effects, never a real portal."""
    source = SOURCE.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(SOURCE))
    by_name = {node.name: node for node in tree.body
               if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    required = ["perform", "received"]
    if any(name not in by_name for name in required):
        raise RuntimeError("inspected pilot no longer exposes these handlers")

    desktop = {"focus": initial_focus, "effects": []}
    peer = FakeConnection(command, os.getuid() if uid is None else uid,
                          desktop, switch_focus=focus_after_peer_check)
    listener = FakeListener(peer)
    state = {"socket": listener, "session": "fake-session"}
    def fake_key(keysym, down):
        desktop["effects"].append((keysym, down, desktop["focus"]))
    def fake_type(text):
        desktop["effects"].append(("type", text, desktop["focus"]))
    env = {
        "socket": socket, "struct": struct, "json": json, "os": os,
        "state": state, "key": fake_key, "send_type": fake_type,
        "remote": types.SimpleNamespace(
            NotifyPointerMotion=lambda *a: None,
            NotifyPointerButton=lambda *a: None),
        "GLib": types.SimpleNamespace(idle_add=lambda *a: None),
        "loop": types.SimpleNamespace(quit=lambda: None),
    }
    selected = ast.Module(body=[by_name[name] for name in required],
                          type_ignores=[])
    exec(compile(ast.fix_missing_locations(selected), str(SOURCE), "exec"),
         env)
    env["received"](0, 0)
    assert peer.closed, "fake handler did not close connection"
    return peer.responses[0], desktop["effects"]


class DesktopSocketAuthorityContract(unittest.TestCase):
    def test_negative_same_uid_without_intent_capability_must_not_enter(self):
        # This is RED against inspected pilot: same Unix UID is accepted.
        response, effects = isolated_controller({"op": "enter"})
        self.assertFalse(response["ok"],
                         "same uid alone must not authorize a send effect")
        self.assertEqual([], effects)

    def test_negative_wrong_target_must_not_enter(self):
        # This is RED: pilot's perform() does not inspect requested target.
        response, effects = isolated_controller({
            "op": "enter", "target_window": "other-person-chat",
            "intent_capability": "not-a-real-token"
        })
        self.assertFalse(response["ok"], "unbound target should be denied")
        self.assertEqual([], effects)

    def test_negative_focus_switch_after_peer_check_must_not_misdirect_input(self):
        # A human changes focus while same-uid socket request is processed.
        # Current handler emits key events to whichever window has focus.
        response, effects = isolated_controller(
            {"op": "enter", "target_window": "gemini"},
            focus_after_peer_check="unrelated-human-chat")
        self.assertEqual([], [x for x in effects
                              if x[-1] == "unrelated-human-chat"],
                         "no input to an unrelated focus is acceptable")

    def test_control_wrong_uid_rejected_without_keyboard_effect(self):
        response, effects = isolated_controller({"op": "enter"},
                                                uid=os.getuid()+1)
        self.assertFalse(response["ok"])
        self.assertEqual([], effects)
        self.assertIn("PermissionError", response["error"])

    def test_control_unknown_operation_is_rejected(self):
        response, effects = isolated_controller({"op": "do-anything"})
        self.assertFalse(response["ok"])
        self.assertEqual([], effects)

    def test_control_ping_is_safe(self):
        response, effects = isolated_controller({"op": "ping"})
        self.assertEqual({"ok": True, "action": "ready"}, response)
        self.assertEqual([], effects)


if __name__ == "__main__":
    unittest.main()
