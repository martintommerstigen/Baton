"""B5: an uncertain send never becomes a retry permit via local receipts."""
import hashlib
import hmac
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from remote_security.receipt_audit import audit_receipt, AuditError


class ReceiptAuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'receipts.sqlite'
        self.key = b'K' * 48
        self.payload = b'approved bytes'
        self.envelope = dict(version=1, sender='sender000', target='target000',
                             message_id='message000', issued_at=100,
                             action='wake_request', payload_sha256=hashlib.sha256(self.payload).hexdigest())
        self.canonical = json.dumps(self.envelope, sort_keys=True, separators=(',', ':'),
                                    ensure_ascii=True, allow_nan=False).encode('ascii')
        self.sig = hmac.new(self.key, self.canonical, hashlib.sha256).hexdigest()
        self.db = sqlite3.connect(self.path)
        self.path.chmod(0o600)
        self.db.execute('CREATE TABLE receipts (sender TEXT, msg TEXT, digest TEXT, state TEXT, PRIMARY KEY(sender,msg))')
        self.db.execute('CREATE TABLE payloads (sender TEXT, msg TEXT, envelope BLOB, payload BLOB, signature TEXT, PRIMARY KEY(sender,msg))')
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def insert(self, payload=True):
        self.db.execute('INSERT INTO receipts VALUES (?,?,?,?)',
                        ('sender000', 'message000', hashlib.sha256(self.canonical).hexdigest(), 'accepted_not_delivered'))
        if payload:
            self.db.execute('INSERT INTO payloads VALUES (?,?,?,?,?)',
                            ('sender000', 'message000', self.canonical, self.payload, self.sig))
        self.db.commit()

    def audit(self, key=None, path=None):
        return audit_receipt(path or str(self.path), 'sender000', 'message000', key or self.key)

    def test_absent_is_unknown_not_safe_to_resend(self):
        self.assertEqual(self.audit(), {'classification':'absent_unknown','send_permitted':False})

    def test_authenticated_payload_still_not_delivery(self):
        self.insert()
        self.assertEqual(self.audit(), {'classification':'present_authenticated_payload',
                          'admission_state':'accepted_not_delivered','send_permitted':False})

    def test_legacy_envelope_only_is_unverified(self):
        self.insert(False)
        self.assertEqual(self.audit()['classification'], 'present_envelope_only_unverified')

    def test_wrong_key_does_not_validate(self):
        self.insert()
        self.assertEqual(self.audit(b'X'*48)['classification'], 'corrupt_untrusted')

    def test_tampered_payload_does_not_validate(self):
        self.insert()
        self.db.execute('UPDATE payloads SET payload=?', (b'tampered',)); self.db.commit()
        self.assertEqual(self.audit()['classification'], 'corrupt_untrusted')

    def test_tampered_envelope_does_not_validate(self):
        self.insert()
        self.db.execute('UPDATE payloads SET envelope=?', (b'{}',)); self.db.commit()
        self.assertEqual(self.audit()['classification'], 'corrupt_untrusted')

    def test_tampered_receipt_state_does_not_validate(self):
        self.insert()
        self.db.execute("UPDATE receipts SET state='verified_wake'"); self.db.commit()
        self.assertEqual(self.audit()['classification'], 'corrupt_untrusted')

    def test_tampered_receipt_digest_does_not_validate(self):
        self.insert()
        self.db.execute("UPDATE receipts SET digest=?", ('0'*64,)); self.db.commit()
        self.assertEqual(self.audit()['classification'], 'corrupt_untrusted')

    def test_orphan_payload_is_not_treated_as_absent(self):
        self.insert()
        self.db.execute('DELETE FROM receipts'); self.db.commit()
        self.assertEqual(self.audit()['classification'], 'corrupt_untrusted')

    def test_tampered_signature_does_not_validate(self):
        self.insert()
        self.db.execute('UPDATE payloads SET signature=?', ('0'*64,)); self.db.commit()
        self.assertEqual(self.audit()['classification'], 'corrupt_untrusted')

    def test_loose_database_permissions_rejected(self):
        self.insert()
        self.path.chmod(0o644)
        with self.assertRaises(AuditError): self.audit()

    def test_missing_file_is_not_created(self):
        absent = self.path.parent/'missing.sqlite'
        with self.assertRaises(AuditError): self.audit(path=str(absent))
        self.assertFalse(absent.exists())

    def test_symlink_and_traversal_rejected(self):
        self.insert()
        link=self.path.parent/'link.sqlite'; link.symlink_to(self.path)
        for p in (str(link), str(self.path.parent/'..'/self.path.parent.name/'receipts.sqlite')):
            with self.subTest(p=p), self.assertRaises((AuditError, ValueError)):
                self.audit(path=p)

    def test_does_not_modify_database(self):
        self.insert()
        before=self.path.read_bytes()
        self.audit()
        self.assertEqual(self.path.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
