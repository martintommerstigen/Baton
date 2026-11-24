import unittest
from baton_wake_receipt import validate_wake_receipt, is_confirmed_wake

class WakeReceiptTests(unittest.TestCase):
    def setUp(self):
        self.request={"id":"a"*32,"target_chat":"/c/6aef341a-d850-83ed-a3b2-c735a215bce3","challenge":"b"*32}
        self.receipt={**self.request,"state":"responded","message_id":"reply-123"}
    def test_structural_confirmation(self):
        self.assertTrue(is_confirmed_wake(self.request,self.receipt))
    def test_delivery_not_wake(self):
        self.assertFalse(is_confirmed_wake(self.request,{**self.receipt,"state":"delivered","message_id":None}))
    def test_wrong_target(self):
        self.assertFalse(is_confirmed_wake(self.request,{**self.receipt,"target_chat":"/c/"+"f"*36}))
    def test_wrong_challenge(self):
        self.assertFalse(is_confirmed_wake(self.request,{**self.receipt,"challenge":"c"*32}))
    def test_no_message(self):
        self.assertFalse(is_confirmed_wake(self.request,{**self.receipt,"message_id":None}))
    def test_extra_fields(self):
        self.assertFalse(validate_wake_receipt(self.request,{**self.receipt,"admin":True}))
    def test_forged_receipt_cannot_be_authenticated(self):
        # A matching envelope is NOT cryptographic evidence of its source.
        self.assertTrue(is_confirmed_wake(self.request,self.receipt))
        # Caller MUST separately verify the message exists in target chat.

if __name__=="__main__":
    unittest.main()
