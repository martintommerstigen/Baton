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
    def test_existing_claim_is_not_overwritten(self):
        (self.root/"inflight").mkdir()
        (self.root/"inflight"/("a"*32+".json")).write_text("existing")
        self.assertIsNone(claim_next(self.root))
        self.assertEqual((self.root/"inflight"/("a"*32+".json")).read_text(),"existing")

if __name__=="__main__":
    unittest.main()
