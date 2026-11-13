"""Negative/positive checks against a real isolated Unix socket, fake effect."""
import os
import json
import subprocess
import sys
from pathlib import Path
import tempfile
from threading import Thread
import unittest

from baton_capability_boundary_trial import Gate, Server, request


class BoundaryTrial(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="spire-capability-")
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "broker.sock"
        self.now = [100.0]
        self.gate = Gate(clock=lambda: self.now[0])
        self.server = Server(self.path, self.gate)
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self._stop)

    def _stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def call(self, target="vev", operation="send", token=""):
        return request(self.path, target=target, operation=operation, token=token)

    def test_same_uid_without_capability_denied(self):
        self.assertFalse(self.call()["ok"])
        self.assertEqual([], self.gate.events)

    def test_wrong_target_does_not_consume_valid_capability(self):
        t = self.gate.grant("vev", "send")
        self.assertFalse(self.call(target="som", token=t)["ok"])
        self.assertTrue(self.call(token=t)["ok"])

    def test_wrong_operation_denied_and_raw_evaluate_not_exposed(self):
        t = self.gate.grant("vev", "send")
        self.assertFalse(self.call(operation="observe", token=t)["ok"])
        self.assertEqual("operation_denied", self.call(operation="Runtime.evaluate",
                                                        token=t)["state"])
        self.assertTrue(self.call(token=t)["ok"])

    def test_single_use_and_no_blind_replay(self):
        t = self.gate.grant("vev", "send")
        self.assertTrue(self.call(token=t)["ok"])
        self.assertFalse(self.call(token=t)["ok"])
        self.assertEqual(1, len(self.gate.events))

    def test_revoked_epoch_rejects_unused_grant(self):
        t = self.gate.grant("vev", "send")
        self.gate.revoke("vev")
        self.assertFalse(self.call(token=t)["ok"])
        self.assertEqual([], self.gate.events)

    def test_expired_grant_rejected(self):
        t = self.gate.grant("vev", "send", ttl=1)
        self.now[0] += 2
        self.assertFalse(self.call(token=t)["ok"])

    def test_simultaneous_same_grant_only_one_effect(self):
        t = self.gate.grant("vev", "send")
        out = []
        workers = [Thread(target=lambda: out.append(self.call(token=t))) for _ in range(12)]
        for worker in workers: worker.start()
        for worker in workers: worker.join(timeout=3)
        self.assertEqual(1, sum(x["ok"] for x in out))
        self.assertEqual(1, len(self.gate.events))

    def test_no_token_leak_in_results_or_effect_journal(self):
        t = self.gate.grant("vev", "send")
        result = self.call(token=t)
        self.assertNotIn(t, str(result))
        self.assertNotIn(t, str(self.gate.events))

    def _independent_process_request(self, token):
        # No bearer in argv: pass it only on child stdin.
        child = ("import sys, json; from baton_capability_boundary_trial "
                 "import request; print(json.dumps(request(sys.argv[1], "
                 "target='vev', operation='send', token=sys.stdin.read())))")
        result = subprocess.run([sys.executable, "-c", child, str(self.path)],
                                input=token, text=True, capture_output=True,
                                check=True, timeout=5)
        return json.loads(result.stdout)

    def test_separate_pid_same_uid_no_grant_denied(self):
        self.assertFalse(self._independent_process_request("")["ok"])
        self.assertEqual([], self.gate.events)

    def test_separate_pid_with_stolen_bearer_still_succeeds(self):
        # This must remain a documented LIMITATION until process separation.
        secret = self.gate.grant("vev", "send")
        self.assertTrue(self._independent_process_request(secret)["ok"])
        self.assertEqual(1, len(self.gate.events))

    def test_stolen_bearer_token_from_same_uid_still_works(self):
        # This is a deliberately POSITIVE demonstration of a limitation:
        # another same-UID client holding the bearer can execute the action.
        # No process identity isolation is established by this design.
        token_minted_for_someone_else = self.gate.grant("vev", "send")
        attacker_holds_same_token = token_minted_for_someone_else
        self.assertTrue(self.call(token=attacker_holds_same_token)["ok"])
        self.assertEqual(1, len(self.gate.events))


if __name__ == "__main__":
    unittest.main()
