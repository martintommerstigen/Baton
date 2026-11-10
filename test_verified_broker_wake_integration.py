"""B1 single-hop broker integration with actual offline ledger and fake UI."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from chatgpt_ui_driver import ChatGPTUIDriver
from run_verified_broker_wake import execute_once
from test_chatgpt_ui_submission import CID, Page
from wake_admission_broker import AdmissionStore
from wake_contract import WakeLedger
from wake_broker_ui import BrokerOutcomeUncertain

SOURCE = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'


class SourceDriver:
    def __init__(self, reply): self.reply = reply
    def is_generating(self, chat): return False
    def read_assistant_turn(self, chat, turn):
        return self.reply


class TargetDriver:
    def __init__(self, ui): self.ui = ui
    def submit_once(self, *args, **kwargs):
        return self.ui.submit_once(*args, **kwargs)
    def observe_reply(self, *args):
        return None  # no fabricated assistant turn in offline fake UI


class VerifiedSingleHopIntegration(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.pause = root / 'PAUSE_UI_WRITES'
        self.store = AdmissionStore(root / 'admission.sqlite3', self.pause, [CID])
        self.ledger = WakeLedger(root / 'wake.sqlite3')
        self.page = Page()
        self.target = TargetDriver(ChatGPTUIDriver(self.page, frozenset({CID})))
        p = patch('chatgpt_ui_driver.PAUSE_FILE', self.pause)
        p.start()
        self.addCleanup(p.stop)
        self.calls = []

    def broker(self, request):
        self.calls.append(request.copy())
        return self.store.request(request)

    def store_state(self):
        with self.store.connect() as db:
            row = db.execute('SELECT state FROM admissions WHERE conversation_id=?',
                             (CID,)).fetchone()
            return row[0] if row else None

    def test_source_verified_then_admit_begin_and_uncertain_without_reply(self):
        source = SourceDriver('BATON_WAKE ' + CID + ' m1')
        result = execute_once(self.ledger, source, self.target, SOURCE, CID,
                              'turn-a', 'm1', 'harmless', self.broker, 0)
        self.assertEqual(result, 'uncertain')
        self.assertEqual([c['op'] for c in self.calls], ['admit', 'begin_click'])
        self.assertEqual(self.store_state(), 'uncertain')
        self.assertEqual(self.page.send.clicks, 1)
        self.assertEqual(self.ledger.state('m1')[1], 'uncertain')
        self.assertEqual(self.ledger.provenance('m1')[2], 'turn-a')

    def test_unverified_source_creates_no_admission_or_wake(self):
        source = SourceDriver('ordinary text')
        with self.assertRaises(PermissionError):
            execute_once(self.ledger, source, self.target, SOURCE, CID,
                         'turn-a', 'm1', 'harmless', self.broker, 0)
        self.assertEqual(self.calls, [])
        self.assertIsNone(self.store_state())
        self.assertIsNone(self.ledger.state('m1'))
        self.assertEqual(self.page.send.clicks, 0)

    def test_restarted_ledger_cannot_replay_uncertain_attempt(self):
        source = SourceDriver('BATON_WAKE ' + CID + ' m1')
        self.assertEqual(execute_once(self.ledger, source, self.target, SOURCE,
                                      CID, 'turn-a', 'm1', 'harmless',
                                      self.broker, 0), 'uncertain')
        self.page.editor.text = ''
        self.ledger = WakeLedger(self.ledger.path)
        result = execute_once(self.ledger, source, self.target, SOURCE, CID,
                              'turn-a', 'm1', 'harmless', self.broker, 0)
        self.assertEqual(result, 'uncertain')
        self.assertEqual(self.page.send.clicks, 1)
        self.assertEqual(len(self.calls), 2)


    def test_a_command_mutated_during_admit_never_clicks_b(self):
        source = SourceDriver('BATON_WAKE ' + CID + ' m1')
        def mutating_broker(request):
            response = self.broker(request)
            if request['op'] == 'admit':
                source.reply = 'A revoked the wake request'
            return response
        with self.assertRaises(BrokerOutcomeUncertain):
            execute_once(self.ledger, source, self.target, SOURCE, CID,
                         'turn-a', 'm1', 'harmless', mutating_broker, 0)
        self.assertEqual([c['op'] for c in self.calls], ['admit'])
        self.assertEqual(self.page.send.clicks, 0)
        self.assertEqual(self.ledger.state('m1')[1], 'uncertain')

    def test_a_command_mutated_after_begin_click_never_retries(self):
        source = SourceDriver('BATON_WAKE ' + CID + ' m1')
        def mutating_broker(request):
            response = self.broker(request)
            if request['op'] == 'begin_click':
                source.reply = 'A revoked the wake request'
            return response
        with self.assertRaises(BrokerOutcomeUncertain):
            execute_once(self.ledger, source, self.target, SOURCE, CID,
                         'turn-a', 'm1', 'harmless', mutating_broker, 0)
        self.assertEqual([c['op'] for c in self.calls], ['admit', 'begin_click'])
        self.assertEqual(self.store_state(), 'uncertain')
        self.assertEqual(self.page.send.clicks, 0)
        self.assertEqual(self.ledger.state('m1')[1], 'uncertain')
        source.reply = 'BATON_WAKE ' + CID + ' m1'
        self.ledger = WakeLedger(self.ledger.path)
        self.assertEqual(execute_once(self.ledger, source, self.target, SOURCE,
                                      CID, 'turn-a', 'm1', 'harmless',
                                      self.broker, 0), 'uncertain')
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(self.page.send.clicks, 0)

    def test_a_command_mutated_between_preflight_and_admit(self):
        class ChangingSource(SourceDriver):
            def __init__(self, reply):
                super().__init__(reply)
                self.reads = 0
            def read_assistant_turn(self, chat, turn):
                self.reads += 1
                if self.reads == 2:
                    self.reply = 'BATON_WAKE ' + CID + ' different-message-id'
                return super().read_assistant_turn(chat, turn)
        source = ChangingSource('BATON_WAKE ' + CID + ' m1')
        with self.assertRaises(BrokerOutcomeUncertain):
            execute_once(self.ledger, source, self.target, SOURCE, CID,
                         'turn-a', 'm1', 'harmless', self.broker, 0)
        self.assertGreaterEqual(source.reads, 2)
        self.assertEqual(self.calls, [])
        self.assertEqual(self.page.send.clicks, 0)
        self.assertEqual(self.ledger.state('m1')[1], 'uncertain')



if __name__ == '__main__':
    unittest.main()
