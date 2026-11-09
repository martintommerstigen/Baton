import unittest
from wake_origin import source_requested_wake, verify_source_turn, discover_source_turn

A='aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'
B='bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb'
C='cccccccc-cccc-cccc-cccc-cccccccccccc'

class Reader:
    def __init__(self,reply): self.reply=reply;self.calls=[]
    def read_assistant_turn(self,chat,turn):
        self.calls.append((chat,turn))
        return self.reply

class MultiReader:
    def __init__(self,turns): self.turns=turns
    def list_assistant_turn_ids(self,chat): return tuple(self.turns)
    def read_assistant_turn(self,chat,turn): return self.turns[turn]

class OriginTests(unittest.TestCase):
    def test_streaming_source_is_not_authorized(self):
        class StreamingReader(MultiReader):
            def is_generating(self,chat): return True
        d=StreamingReader({'origin':'BATON_WAKE '+B+' m1'})
        self.assertIsNone(discover_source_turn(d,A,B,'m1'))
        with self.assertRaises(RuntimeError):
            verify_source_turn(d,A,'origin',B,'m1')
    def test_auto_discover_unique_source(self):
        d=MultiReader({'old':'ordinary response','origin':'BATON_WAKE '+B+' m1'})
        self.assertEqual(discover_source_turn(d,A,B,'m1'),'origin')
        self.assertIsNone(discover_source_turn(d,A,B,'m2'))
    def test_duplicate_source_fails_closed(self):
        d=MultiReader({'one':'BATON_WAKE '+B+' m1','two':'BATON_WAKE '+B+' m1'})
        with self.assertRaises(RuntimeError): discover_source_turn(d,A,B,'m1')
    def test_exact_command(self):
        self.assertTrue(source_requested_wake('BATON_WAKE '+B+' m1',B,'m1'))
        self.assertFalse(source_requested_wake('I request a wake.\nBATON_WAKE '+B+' m1',B,'m1'))
        self.assertFalse(source_requested_wake('```\nBATON_WAKE '+B+' m1\n```',B,'m1'))
        self.assertFalse(source_requested_wake('BATON_WAKE '+C+' m1',B,'m1'))
        self.assertFalse(source_requested_wake('BATON_WAKE '+B+' m2',B,'m1'))
        self.assertFalse(source_requested_wake('BATON_WAKE '+B+' m1\nBATON_WAKE '+B+' m1',B,'m1'))
        self.assertFalse(source_requested_wake('BATON_WAKE '+B+' m1 extra',B,'m1'))
        self.assertFalse(source_requested_wake('BATON_WAKE '+B+' m1\nBATON_WAKE '+C+' m2',B,'m1'))
        self.assertFalse(source_requested_wake('',B,'m1'))
    def test_reject_bad_id(self):
        with self.assertRaises(ValueError):
            source_requested_wake('anything',B,'../bad')
    def test_provenance_is_read_from_source(self):
        reader=Reader('BATON_WAKE '+B+' m1')
        self.assertTrue(verify_source_turn(reader,A,'assistant-turn-1',B,'m1'))
        self.assertEqual(reader.calls,[(A,'assistant-turn-1')])
    def test_wrong_turn_command_fails_closed(self):
        reader=Reader('BATON_WAKE '+C+' m1')
        with self.assertRaises(PermissionError):
            verify_source_turn(reader,A,'assistant-turn-1',B,'m1')
    def test_missing_turn_id_fails_closed(self):
        reader=Reader('BATON_WAKE '+B+' m1')
        with self.assertRaises(ValueError):
            verify_source_turn(reader,A,'',B,'m1')
        self.assertEqual(reader.calls,[])

if __name__=='__main__': unittest.main()
