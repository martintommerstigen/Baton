"""Baton focus-switch race: deterministic model, not a Qt/Wayland integration.

Motivation: Søm's source-bound continuity-rhythm post 86957e86:
a valid epoch and exclusive agent seat lease do not prove the human has not
changed keyboard focus between validation and physical input.

This module contains a counterexample harness and a deliberately conservative
adapter contract. Nothing here sends real key events or changes the active
Baton worker, portal session or desktop.
"""
from dataclasses import dataclass
import unittest


@dataclass(frozen=True)
class Permit:
    intended_window: str
    epoch: int
    route: str


class FakeWayland:
    """Human focus changes are outside the agent's resource lock."""
    def __init__(self, focused):
        self.focused = focused
        self.epoch = 7
        self.effects = []
        self.audit = []

    def check_epoch(self, permit):
        return permit.epoch == self.epoch

    def human_focus(self, window):
        self.focused = window

    def focus_based_key(self, key):
        actual_target = self.focused
        self.effects.append(("key", key, actual_target))
        return actual_target

    def target_bound_key(self, window, key):
        # Models an actual adapter that can bind the OS effect to an exact
        # window at its final non-interleavable effect boundary. This is an
        # ASSUMPTION, not a claim that a KDE portal implements such a method.
        self.effects.append(("bound-key", key, window))
        return window


def unsafe_split_check_then_input(seat, permit, key, between_check_and_input):
    """Counterexample: check at dequeue is not atomic with global focus."""
    if not seat.check_epoch(permit) or seat.focused != permit.intended_window:
        seat.audit.append("blocked_before_input")
        return False
    between_check_and_input()
    delivered = seat.focus_based_key(key)
    seat.audit.append("committed_to_" + delivered)
    return delivered == permit.intended_window


def guarded_effect(seat, permit, key, between_validation_and_effect, *,
                   bound_effect_supported):
    """Fail closed unless the actual effect is target-bound, not just checked."""
    if not seat.check_epoch(permit):
        seat.audit.append("mandate_revoked")
        return False
    between_validation_and_effect()
    if not seat.check_epoch(permit):
        seat.audit.append("mandate_revoked_before_effect")
        return False
    if not bound_effect_supported:
        seat.audit.append("unsupported_target_binding_no_input")
        return False
    delivered = seat.target_bound_key(permit.intended_window, key)
    seat.audit.append("committed_to_" + delivered)
    return True


class FocusSwitchTrial(unittest.TestCase):
    def setUp(self):
        self.seat = FakeWayland("chat-vev")
        self.permit = Permit("chat-vev", 7, "wayland-seat0")

    def test_negative_control_epoch_and_seat_lease_do_not_prevent_wrong_window(self):
        # Epoch remains valid and agent seat ownership is uncontested.
        # Human focus shift occurs AFTER all Python-level checks.
        result = unsafe_split_check_then_input(
            self.seat, self.permit, "Enter",
            lambda: self.seat.human_focus("unrelated-human-window"))
        self.assertFalse(result)
        self.assertEqual([("key", "Enter", "unrelated-human-window")],
                         self.seat.effects)
        # Never label this effect as canceled or safely delivered to Vev.
        self.assertIn("committed_to_unrelated-human-window", self.seat.audit)

    def test_fail_closed_when_desktop_adapter_lacks_target_bound_effect(self):
        result = guarded_effect(
            self.seat, self.permit, "Enter",
            lambda: self.seat.human_focus("unrelated-human-window"),
            bound_effect_supported=False)
        self.assertFalse(result)
        self.assertEqual([], self.seat.effects)
        self.assertEqual("unsupported_target_binding_no_input",
                         self.seat.audit[-1])

    def test_true_target_bound_effect_is_independent_of_human_focus(self):
        result = guarded_effect(
            self.seat, self.permit, "Enter",
            lambda: self.seat.human_focus("unrelated-human-window"),
            bound_effect_supported=True)
        self.assertTrue(result)
        self.assertEqual([("bound-key", "Enter", "chat-vev")],
                         self.seat.effects)

    def test_focus_check_twice_is_still_not_an_atomic_target_binding(self):
        # Even two checks can be raced after the second check; a seat lock
        # held only by automation does not fence a human desktop focus change.
        def after_last_check():
            self.assertEqual("chat-vev", self.seat.focused)
            self.seat.human_focus("personal-chat")
        result = unsafe_split_check_then_input(
            self.seat, self.permit, "Enter", after_last_check)
        self.assertFalse(result)
        self.assertEqual("personal-chat", self.seat.effects[0][-1])

    def test_revoked_epoch_stops_target_bound_effect_even_if_focus_stable(self):
        self.seat.epoch += 1
        result = guarded_effect(self.seat, self.permit, "Enter",
                                lambda: None, bound_effect_supported=True)
        self.assertFalse(result)
        self.assertEqual([], self.seat.effects)

    def test_separate_cdp_route_not_blocked_by_wayland_focus_unavailability(self):
        gui = guarded_effect(
            self.seat, self.permit, "Enter", lambda: None,
            bound_effect_supported=False)
        cdp_sink = []
        cdp_sink.append(("cdp-send", "chat-siv", "fresh-intent"))
        self.assertFalse(gui)
        self.assertEqual([], self.seat.effects)
        self.assertEqual([("cdp-send", "chat-siv", "fresh-intent")], cdp_sink)


if __name__ == "__main__":
    unittest.main()
