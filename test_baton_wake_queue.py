import tempfile
import unittest
from pathlib import Path
from baton_wake_queue import WakeIntent, enqueue

class WakeQueueTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)/"queue"
        self.intent = WakeIntent("a"*32,"6aef828e-0150-83eb-bbac-061f79a8fd4a","Wake test")
    def test_create_once(self):
        path=enqueue(self.root,self.intent)
        self.assertTrue(path.is_file())
        with self.assertRaises(ValueError):
            enqueue(self.root,self.intent)
    def test_invalid_target(self):
        with self.assertRaises(ValueError):
            WakeIntent("a"*32,"../elsewhere","Wake test")
    def test_empty_message(self):
        with self.assertRaises(ValueError):
            WakeIntent("a"*32,self.intent.chat_id,"")
    def test_oversized_message(self):
        with self.assertRaises(ValueError):
            WakeIntent("a"*32,self.intent.chat_id,"x"*4001)
    def test_symlinked_queue(self):
        self.root.symlink_to(Path(self.temp.name))
        with self.assertRaises(ValueError):
            enqueue(self.root,self.intent)

if __name__=="__main__":
    unittest.main()
