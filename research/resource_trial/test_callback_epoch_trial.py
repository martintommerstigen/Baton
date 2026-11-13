"""Deterministic dispatcher model; no Qt, portal or real input.

Counterexample from Siv, Baton post 9c29a228-4c2c-481d-8c14-54275b71a338.
The commit point here is an explicitly modelled boundary, not an OS guarantee.
"""
from dataclasses import dataclass
from threading import Lock
import unittest


@dataclass(frozen=True)
class Callback:
    scope: str
    epoch: int


class Dispatcher:
    def __init__(self, recheck=True):
        self.lock = Lock()
        self.epochs = {}
        self.enabled = {}
        self.sink = []
        self.journal = []
        self.recheck = recheck

    def enqueue(self, scope):
        with self.lock:
            if not self.enabled.get(scope, True):
                raise PermissionError(scope)
            return Callback(scope, self.epochs.get(scope, 0))

    def revoke(self, scope):
        with self.lock:
            self.epochs[scope] = self.epochs.get(scope, 0) + 1
            self.enabled[scope] = False
            self.journal.append((scope, 'revoked'))

    def commit(self, cb):
        with self.lock:
            if self.recheck and (not self.enabled.get(cb.scope, True)
                                 or cb.epoch != self.epochs.get(cb.scope, 0)):
                self.journal.append((cb.scope, 'canceled_before_commit'))
                return False
            # In this MODEL only, check and sink append are one critical section.
            self.sink.append(cb.scope)
            self.journal.append((cb.scope, 'effect_committed'))
            return True


class CallbackEpochTrial(unittest.TestCase):
    def run_delayed(self, recheck):
        d = Dispatcher(recheck)
        gui = d.enqueue('wayland-seat0')
        cdp = d.enqueue('cdp-target-B')
        d.revoke('wayland-seat0')
        d.commit(gui)
        d.commit(cdp)
        return d

    def test_revoke_queued_callback_before_commit_cancels_only_its_scope(self):
        d = self.run_delayed(True)
        self.assertEqual(d.sink, ['cdp-target-B'])
        self.assertIn(('wayland-seat0', 'canceled_before_commit'), d.journal)
        self.assertIn(('cdp-target-B', 'effect_committed'), d.journal)

    def test_negative_control_enqueue_check_alone_violates_same_invariant(self):
        d = self.run_delayed(False)
        # The unsafe dispatcher really emits the revoked effect.
        self.assertEqual(d.sink, ['wayland-seat0', 'cdp-target-B'])
        with self.assertRaises(AssertionError):
            self.assertEqual(d.sink, ['cdp-target-B'])

    def test_revoke_before_commit_linearization(self):
        d = Dispatcher(); cb = d.enqueue('gui')
        d.revoke('gui')
        self.assertFalse(d.commit(cb))
        self.assertEqual(d.sink, [])

    def test_commit_before_revoke_does_not_claim_physical_undo(self):
        d = Dispatcher(); cb = d.enqueue('gui')
        self.assertTrue(d.commit(cb)); d.revoke('gui')
        self.assertEqual(d.sink, ['gui'])
        self.assertNotIn(('gui', 'canceled_before_commit'), d.journal)

    def test_revoked_scope_cannot_enqueue_new_callbacks(self):
        d = Dispatcher(); d.revoke('gui')
        with self.assertRaises(PermissionError): d.enqueue('gui')
        self.assertTrue(d.commit(d.enqueue('cdp')))


if __name__ == '__main__':
    unittest.main()
