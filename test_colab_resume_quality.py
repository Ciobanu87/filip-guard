import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
import colab_resume_quality as resume


class ColabResumeTests(unittest.TestCase):
    def test_missing_history_stops_before_network_and_preserves_objects(self):
        old=object();namespace={'ledger':'/nonexistent-fil ip-guard-ledger','advisor':old}
        with patch.object(resume.subprocess,'run') as network:
            with self.assertRaises(RuntimeError):resume.run(namespace)
        network.assert_not_called();self.assertIs(namespace['advisor'],old)

    def test_existing_ledger_is_only_inspected_without_resetting_budget(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger=Path(directory)/'ledger.sqlite'
            with sqlite3.connect(ledger) as db:
                db.execute('CREATE TABLE advisor_requests (result TEXT)')
                db.execute('INSERT INTO advisor_requests VALUES (?)',('accepted',))
                db.execute('CREATE TABLE advisor_budget (calls INTEGER)')
                db.execute('INSERT INTO advisor_budget VALUES (17)')
            before=ledger.read_bytes()
            self.assertEqual(resume.existing_ledger({'advisor':SimpleNamespace(path=ledger)}),ledger)
            self.assertEqual(ledger.read_bytes(),before)

    def test_missing_completed_fixtures_blocks_without_inference(self):
        fixtures=Mock(return_value={'documentation':{}})
        with self.assertRaisesRegex(RuntimeError,'international, nonprofit'):
            resume.completed_required(object(),fixtures,lambda:[])
        fixtures.assert_called_once()

    def test_exact_three_historical_cases_are_required_not_new_provider_responses(self):
        completed={name:{} for name in resume.REQUIRED}
        fixtures=Mock(return_value=completed);advisor=object()
        self.assertIs(resume.completed_required(advisor,fixtures,lambda:['fixture']),completed)
        fixtures.assert_called_once_with(advisor,['fixture'])
