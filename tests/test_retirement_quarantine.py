"""Isolated B5 policy tests; synthetic attestations are NOT live UI proof."""
import concurrent.futures
import hashlib
import os
from pathlib import Path
import socket
import tempfile
import unittest
from remote_security.retirement_quarantine import Quarantine, evaluate_candidate, kernel_peer_uid


class QuarantineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.root.chmod(0o700)
        self.db = self.root / 'evidence.sqlite'
        self.q = Quarantine(str(self.db))
        self.admission = dict(conversation_id='chat-B', message_id='m1', origin_turn_id='turn-A',
                              sender_id='chat-A', payload_sha256=hashlib.sha256(b'approved').hexdigest(),
                              state='uncertain')
        self.receipt = dict(self.admission, state='verified', observed_user_turn_id='turn-B-user',
                            observed_assistant_turn_id='turn-B-assistant')
        self.creds = dict(peer_uid=20002, trusted_attestor_uid=20002, broker_uid=20001)

    def record(self, admission=None, receipt=None, **overrides):
        return self.q._record_authenticated(admission or self.admission, receipt or self.receipt,
                             **dict(self.creds, **overrides))

    def test_candidate_never_retires(self):
        self.assertEqual(self.record(), 'candidate_quarantined_not_retired')
        self.assertEqual(self.q.status('chat-B')['state'], 'quarantined_not_retired')

    def test_replay_is_deduplicated(self):
        self.record()
        self.assertEqual(self.record(), 'duplicate_quarantined_not_retired')

    def test_restart_preserves_quarantine(self):
        self.record()
        self.q = Quarantine(str(self.db))
        self.assertEqual(self.record(), 'duplicate_quarantined_not_retired')

    def test_new_message_same_target_is_conflict(self):
        self.record()
        a = dict(self.admission, message_id='m2')
        r = dict(self.receipt, message_id='m2')
        self.assertEqual(self.record(a, r), 'conflict_quarantined_not_retired')

    def test_target_substitution_rejected(self):
        self.assertEqual(self.record(receipt=dict(self.receipt, conversation_id='chat-C')), 'reject_binding_mismatch')

    def test_payload_substitution_rejected(self):
        self.assertEqual(self.record(receipt=dict(self.receipt, payload_sha256='0'*64)), 'reject_binding_mismatch')

    def test_origin_substitution_rejected(self):
        self.assertEqual(self.record(receipt=dict(self.receipt, origin_turn_id='turn-X')), 'reject_binding_mismatch')

    def test_untrusted_peer_rejected(self):
        self.assertEqual(self.record(peer_uid=20003), 'reject_untrusted_attestor')

    def test_same_uid_broker_and_attestor_rejected(self):
        self.assertEqual(self.record(broker_uid=20002), 'reject_untrusted_attestor')

    def test_admitted_not_uncertain_rejected(self):
        self.assertEqual(self.record(admission=dict(self.admission, state='admitted')), 'reject_not_uncertain')

    def test_unverified_receipt_rejected(self):
        self.assertEqual(self.record(receipt=dict(self.receipt, state='pending')), 'reject_unverified_receipt')

    def test_missing_turn_id_rejected(self):
        self.assertEqual(self.record(receipt=dict(self.receipt, observed_assistant_turn_id='')), 'reject_missing_turn_ids')

    def test_same_user_assistant_turn_rejected(self):
        self.assertEqual(self.record(receipt=dict(self.receipt, observed_assistant_turn_id='turn-B-user')), 'reject_colliding_turn_ids')

    def test_origin_turn_reuse_rejected(self):
        self.assertEqual(self.record(receipt=dict(self.receipt, observed_assistant_turn_id='turn-A')), 'reject_reused_origin_turn')

    def test_concurrent_identical_candidate_only_one_insert(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            out = list(pool.map(lambda _: self.record(), range(16)))
        self.assertEqual(out.count('candidate_quarantined_not_retired'), 1)
        self.assertEqual(out.count('duplicate_quarantined_not_retired'), 15)

    def test_concurrent_conflicting_candidates_never_release(self):
        a = dict(self.admission, message_id='m2')
        r = dict(self.receipt, message_id='m2')
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda pair: self.record(*pair), [(self.admission, self.receipt), (a, r)]))
        self.assertEqual(sorted(results), sorted(['candidate_quarantined_not_retired', 'conflict_quarantined_not_retired']))

    def test_symlink_db_rejected(self):
        other = self.root / 'other'
        other.write_bytes(b'x')
        self.db.unlink()
        self.db.symlink_to(other)
        with self.assertRaises(ValueError):
            Quarantine(str(self.db))

    def test_world_readable_db_rejected(self):
        self.db.chmod(0o644)
        with self.assertRaises(PermissionError):
            Quarantine(str(self.db))

    def test_world_readable_parent_rejected(self):
        self.root.chmod(0o755)
        with self.assertRaises(PermissionError):
            Quarantine(str(self.root / 'new.sqlite'))

    def test_kernel_peer_uid_uses_socket_not_sender(self):
        a, b = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            self.assertEqual(kernel_peer_uid(a), os.getuid())
            self.assertEqual(kernel_peer_uid(b), os.getuid())
        finally:
            a.close(); b.close()

    def test_cross_target_reuse_of_turn_ids_rejected(self):
        self.record()
        a = dict(self.admission, conversation_id="chat-C", message_id="m2")
        r = dict(self.receipt, conversation_id="chat-C", message_id="m2")
        self.assertEqual(self.record(a, r), "cross_target_turn_reuse_quarantined")

    def test_distinct_target_and_distinct_turns_quarantined(self):
        self.record()
        a = dict(self.admission, conversation_id="chat-C", message_id="m2")
        r = dict(self.receipt, conversation_id="chat-C", message_id="m2", observed_user_turn_id="user-C", observed_assistant_turn_id="assistant-C")
        self.assertEqual(self.record(a, r), "candidate_quarantined_not_retired")

    def test_real_socket_rejects_same_uid_attestor(self):
        a, b = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            self.assertEqual(self.q.record_from_socket(a, self.admission, self.receipt, trusted_attestor_uid=os.geteuid()), "reject_untrusted_attestor")
        finally:
            a.close(); b.close()

    def test_symlink_ancestor_rejected(self):
        link = self.root / "link"
        link.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(ValueError):
            Quarantine(str(link / "new.sqlite"))

    def test_parent_traversal_rejected(self):
        with self.assertRaises(ValueError):
            Quarantine(str(self.root) + "/../" + self.root.name + "/new.sqlite")

    def test_invalid_path_rejected(self):
        with self.assertRaises(ValueError):
            Quarantine('relative.sqlite')

    def test_no_browser_or_admission_side_effect(self):
        before = self.db.stat()
        self.record()
        self.assertTrue(self.db.exists())
        self.assertEqual(before.st_ino, self.db.stat().st_ino)
        self.assertEqual(set(p.name for p in self.root.iterdir()), {'evidence.sqlite'})


if __name__ == '__main__':
    unittest.main()
