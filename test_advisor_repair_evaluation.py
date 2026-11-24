import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from advisor_diagnostics import AdvisorFailure
from advisor_groq import GroqFreeProvider
from contextual_advisor import ContextualAdvisor
from validate_cloud_advisor import run_validation
from test_advisor_groq import KEY,response,indexed_selection
from test_contextual_advisor import ROWS,CONTEXT,SCOPE

class RepairedEvaluationTests(unittest.TestCase):
    def engine(self,root):
        self.now=100.0
        return ContextualAdvisor(Path(root)/'ledger.sqlite',GroqFreeProvider(lambda:KEY,free_plan_confirmed=True,data_consent=True),clock=lambda:self.now)
    def wait(self,seconds):self.now+=seconds
    def valid(self,body,*args):return response(indexed_selection(json.loads(json.loads(body)['messages'][1]['content'])))
    def test_all_seven_indexed_contract_cases_are_accepted_without_claiming_real_inference(self):
        with tempfile.TemporaryDirectory() as root,patch('advisor_groq.cloud_exchange',side_effect=self.valid):
            report=run_validation(self.engine(root),wait=self.wait)
        self.assertEqual(report['accepted_ai_cases'],7);self.assertFalse(report['real_inference_executed']);self.assertFalse(report['quality_validated'])
        romanian=next(x for x in report['cases'] if x['language']=='ro')
        self.assertEqual(romanian['rendered_language'],'ro');self.assertIn('Redactează',romanian['review_sample']['solution'])
        self.assertIn('Dovadă observată',romanian['review_sample']['reason'])
        self.assertTrue(all(x['review_sample']['cause'] and x['review_sample']['impact'] for x in report['cases']))
        self.assertTrue(all(x['human_relevance_score'] is None for x in report['cases']))
        self.assertNotIn(KEY,json.dumps(report))
    def test_auth_schema_model_or_quota_failure_stops_remaining_calls(self):
        for status in [400,401,403,404,422,429]:
            with tempfile.TemporaryDirectory() as root,patch('advisor_groq.cloud_exchange',side_effect=AdvisorFailure('http_error','http',http_status=status)) as call:
                report=run_validation(self.engine(root),wait=self.wait)
            self.assertTrue(report['stopped_early']);self.assertEqual(report['attempted_cases'],1);call.assert_called_once()
            self.assertEqual(report['accepted_ai_cases'],0);self.assertEqual(report['cases'][0]['diagnostic']['http_status'],status)
            self.assertTrue(all(x['status']=='not-run' for x in report['cases'][1:]))
    def test_repeated_network_timeouts_stop_after_two_attempts_with_stage(self):
        with tempfile.TemporaryDirectory() as root,patch('advisor_groq.cloud_exchange',side_effect=AdvisorFailure('timeout','read')) as call:
            report=run_validation(self.engine(root),wait=self.wait)
        self.assertEqual(call.call_count,2);self.assertEqual(report['attempted_cases'],2);self.assertEqual(report['cases'][1]['diagnostic']['stage'],'read')
    def test_language_switch_uses_cached_selection_and_does_not_spend_another_call(self):
        with tempfile.TemporaryDirectory() as root,patch('advisor_groq.cloud_exchange',side_effect=self.valid) as call:
            engine=self.engine(root)
            english=engine.analyze(ROWS,CONTEXT,scope=SCOPE)
            romanian=engine.analyze(ROWS,CONTEXT,scope=SCOPE,language='ro')
        call.assert_called_once();self.assertEqual(english['language'],'en');self.assertEqual(romanian['language'],'ro')
        self.assertFalse(romanian['recommendations'][0]['root_cause_verified'])
        self.assertEqual(english['recommendations'][0]['seo_draft'],romanian['recommendations'][0]['seo_draft'])
    def test_notebook_refreshes_revision_and_imports_without_resetting_budget_or_key(self):
        notebook=json.loads(Path('notebooks/validate_cloud_advisor.ipynb').read_text())
        setup=''.join(notebook['cells'][1]['source'])
        self.assertIn('ls-remote',setup);self.assertIn('del sys.modules[name]',setup)
        self.assertIn('source.backup(target)',setup);self.assertNotIn('rmtree',setup)
        for cell in notebook['cells']:
            if cell['cell_type']=='code':compile(''.join(cell['source']),'colab-cell','exec')
