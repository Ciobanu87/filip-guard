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

    def test_exact_eight_historical_cases_are_required_not_new_provider_responses(self):
        completed={name:{} for name in resume.REQUIRED}
        fixtures=Mock(return_value=completed);advisor=object()
        self.assertIs(resume.completed_required(advisor,fixtures,lambda:['fixture']),completed)
        fixtures.assert_called_once_with(advisor,['fixture'])

    def test_only_three_old_results_are_insufficient_for_single_heading_continuation(self):
        fixtures=Mock(return_value={name:{} for name in ('documentation','nonprofit','international')})
        with self.assertRaisesRegex(RuntimeError,'Niciun apel nou'):
            resume.completed_required(object(),fixtures,lambda:[])
        self.assertEqual(len(resume.REQUIRED),8)
        self.assertNotIn('heading-context-en',resume.REQUIRED)

    def test_full_helper_preserves_eight_results_and_only_calls_heading_once(self):
        import json
        import sys
        from unittest.mock import patch
        import test_advisor_quality_evaluation as quality_tests
        from test_advisor_groq import KEY,indexed_selection,response
        from advisor_quality_evaluation import run_quality_evaluation
        fixture=quality_tests.QualityContinuationTests();fixture.setUp()
        try:
            def seed(body,*args):
                bundle=json.loads(json.loads(body)['messages'][1]['content'])
                if any(f['problem']=='H1 structure needs review' for f in bundle['findings']):
                    payload=indexed_selection(bundle);payload['recommendations']['f0']['evidence_id']='p9e0'
                    return response(payload)
                return fixture.valid(body,*args)
            with patch('advisor_groq.cloud_exchange',side_effect=seed):
                first=run_quality_evaluation(fixture.engine,wait=fixture.wait)
            self.assertEqual(first['accepted_ai_cases'],8);fixture.now+=7200
            with tempfile.TemporaryDirectory() as directory:
                checkout=Path(directory)
                colab=SimpleNamespace(userdata=SimpleNamespace(get=Mock(return_value=KEY)),files=SimpleNamespace(download=Mock()))
                namespace={'ledger':fixture.engine.path}
                def mapped_path(value):
                    return checkout if str(value).startswith('/content/filip-guard-ai-validation-') else Path(value)
                def evaluate(advisor,**kwargs):
                    advisor.clock=lambda:fixture.now
                    return run_quality_evaluation(advisor,wait=fixture.wait,**kwargs)
                with patch.object(resume,'Path',side_effect=mapped_path),patch.object(resume.subprocess,'check_output',return_value=resume.REVISION),patch.dict(sys.modules,{'google.colab':colab}),patch('advisor_quality_evaluation.run_quality_evaluation',side_effect=evaluate),patch('advisor_groq.cloud_exchange',side_effect=fixture.valid) as api,patch('builtins.print'):
                    report=resume.run(namespace)
                self.assertEqual(api.call_count,1)
                colab.userdata.get.assert_called_once_with('GROQ_API_KEY')
                colab.files.download.assert_called_once()
                self.assertEqual(report['completed_before_this_run'],8)
                self.assertEqual(report['accepted_ai_cases'],9)
                self.assertFalse(report['quality_validated'])
                self.assertNotIn(KEY,namespace['report_path'].read_text())
                self.assertEqual(namespace['report_path'].stat().st_mode & 0o777,0o600)
        finally:fixture.temp.cleanup()
