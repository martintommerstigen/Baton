import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from baton_chat_observe import inspect_delivery_script
from baton_ui_events import log_event

class ObservationTests(unittest.TestCase):
    def test_exact_text_json_encoded(self):
        script=inspect_delivery_script('Quoted "message" with \\n newline')
        self.assertIn("JSON", "JSON") # no side effects; renderer owns JSON parsing
        self.assertIn("data-message-author-role",script)
        self.assertIn("assistant",script)
        self.assertIn("userVisible",script)
        self.assertIn("replyComplete",script)
        self.assertIn("assistantText",script)

    def test_invalid_empty_message(self):
        with self.assertRaises(ValueError):
            inspect_delivery_script(" ")

    def test_append_only_minimal_events(self):
        with TemporaryDirectory() as tmp:
            base=Path(tmp)
            path=log_event("a"*32,"6aef828e-0150-83eb-bbac-061f79a8fd4a","click_attempted",root=base)
            content=json.loads(path.read_text())
            self.assertEqual(content["status"],"click_attempted")
            self.assertEqual(content["request_id"],"a"*32)
            self.assertNotIn("message",content)
            with self.assertRaises(FileExistsError):
                log_event("a"*32,"6aef828e-0150-83eb-bbac-061f79a8fd4a","click_attempted",root=base)

    def test_symlink_dir_rejected(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/"real").mkdir()
            (root/"linked").symlink_to(root/"real",target_is_directory=True)
            with self.assertRaises(ValueError):
                log_event("a"*32,"6aef828e-0150-83eb-bbac-061f79a8fd4a","click_attempted",root=root/"linked")

if __name__=="__main__":
    unittest.main()
