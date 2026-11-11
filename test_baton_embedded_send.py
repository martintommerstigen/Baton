import unittest
from baton_embedded_send import may_send, prepare_send_script, send_click_script, clear_prepared_script

class EmbeddedSendTests(unittest.TestCase):
    def test_target(self):
        chat="6aef828e-0150-83eb-bbac-061f79a8fd4a"
        self.assertTrue(may_send("https://chatgpt.com/c/"+chat,chat))
        self.assertFalse(may_send("https://chatgpt.com/c/other",chat))
    def test_escaped_message(self):
        script=prepare_send_script('hello "quoted"\nline')
        self.assertIn('hello \\"quoted\\"\\nline',script)
        self.assertIn('composer-not-found',script)
    def test_empty_rejected(self):
        with self.assertRaises(ValueError):
            prepare_send_script("")
    def test_current_composer_variants(self):
        script=prepare_send_script('probe')
        self.assertIn("'#prompt-textarea'",script)
        self.assertIn("'.ProseMirror[contenteditable]'",script)
        self.assertIn("'[role=\"textbox\"][contenteditable]'",script)
        self.assertIn("'form textarea'",script)
        self.assertIn('item.isContentEditable',script)
        self.assertIn('composer-not-empty',script)
        self.assertIn('composer-insertion-not-verified',script)
        self.assertIn('editor-candidates=',script)
    def test_send_guard_checks_same_draft(self):
        script=send_click_script('baton probe')
        self.assertIn('baton probe',script)
        self.assertIn('composer-changed-before-send',script)
        self.assertIn('composer-lost-before-send',script)
        self.assertIn('clicked-not-delivery-proof',script)
    def test_draft_escaped_in_send_guard(self):
        script=send_click_script('one "quote"\\ntwo')
        self.assertIn('one \\"quote\\"\\\\ntwo',script)
    def test_send_current_composer_submit_selector(self):
        script=send_click_script("Baton probe")
        self.assertIn("button#composer-submit-button",script)
        self.assertIn("button.composer-submit-btn",script)
        self.assertIn("composerForm.querySelectorAll",script)
        self.assertIn("node.closest('form') !== composerForm",script)
        self.assertIn("enabled.length !== 1",script)
        self.assertIn("candidate-count=",script)
        self.assertIn("clicked-not-delivery-proof",script)
    def test_clear_only_exact_prepared_unsent_draft(self):
        script=clear_prepared_script("Baton probe")
        self.assertIn('value !== expected',script)
        self.assertIn('draft-was-changed',script)
        self.assertIn('cleared-only-baton-draft',script)
        self.assertIn("document.execCommand('delete'",script)
        self.assertNotIn("document.querySelector('body').innerHTML",script)
    def test_no_unauthorized_cleanup(self):
        script=clear_prepared_script('draft "quoted"\\nsecond line')
        self.assertIn('draft \\"quoted\\"\\\\nsecond line',script)

    def test_send_script_requires_enabled_button(self):
        script=send_click_script()
        self.assertIn("send-button",script)
        self.assertIn("!node.disabled",script)
        self.assertIn("clicked-not-delivery-proof",script)
if __name__=="__main__":
    unittest.main()
