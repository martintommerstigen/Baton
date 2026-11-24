import tempfile
import unittest
from pathlib import Path
from baton_wake_queue import WakeIntent, enqueue
from baton_wake_claim import claim_next

class WakeClaimTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.intent=WakeIntent("a"*32,"6aef828e-0150-83eb-bbac-061f79a8fd4a","Hello")
        enqueue(self.root/"queued",self.intent)
    def test_claim_once(self):
        self.assertEqual(claim_next(self.root),self.intent)
        self.assertIsNone(claim_next(self.root))
    def test_claim_persists_across_restart(self):
        claim_next(self.root)
        self.assertTrue((self.root/"inflight"/("a"*32+".json")).exists())
        self.assertIsNone(claim_next(self.root))
    def test_reject_linked_root(self):
        alias=Path(self.tmp.name+"-alias")
        alias.symlink_to(self.root)
        self.addCleanup(alias.unlink)
        with self.assertRaises(ValueError):
            claim_next(alias)
    def test_invalid_request_does_not_block_valid_request(self):
        bad = self.root/"queued"/("0"*32+".json")
        bad.write_text("{invalid", encoding="utf-8")
        self.assertEqual(claim_next(self.root), self.intent)
        self.assertFalse((self.root/"inflight"/bad.name).exists())
    def test_mismatched_id_does_not_claim(self):
        bad = self.root/"queued"/("0"*32+".json")
        bad.write_text((self.root/"queued"/("a"*32+".json")).read_text())
        self.assertEqual(claim_next(self.root), self.intent)
        self.assertFalse((self.root/"inflight"/bad.name).exists())
    def test_oversized_request_does_not_claim(self):
        bad = self.root/"queued"/("0"*32+".json")
        bad.write_text("x"*8193)
        self.assertEqual(claim_next(self.root), self.intent)
        self.assertFalse((self.root/"inflight"/bad.name).exists())
    def test_existing_claim_is_not_overwritten(self):
        (self.root/"inflight").mkdir()
        (self.root/"inflight"/("a"*32+".json")).write_text("existing")
        self.assertIsNone(claim_next(self.root))
        self.assertEqual((self.root/"inflight"/("a"*32+".json")).read_text(),"existing")

if __name__=="__main__":
    unittest.main()
