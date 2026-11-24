import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from advisor_groq import GroqFreeProvider
from contextual_advisor import ContextualAdvisor
from validate_cloud_advisor import run_validation
from test_advisor_groq import KEY,response,indexed_selection
from test_contextual_advisor import selection,SimulatedProvider

class CloudEvaluationTests(unittest.TestCase):
    def test_seven_cases_use_existing_validator_and_honestly_mark_mocked_api(self):
        now=[100.0]
        with tempfile.TemporaryDirectory() as root:
            provider=GroqFreeProvider(lambda:KEY,free_plan_confirmed=True,data_consent=True)
            advisor=ContextualAdvisor(Path(root)/'ledger.sqlite',provider,daily_calls=7,clock=lambda:now[0])
            def wait(seconds):self.assertEqual(seconds,61);now[0]+=seconds
            def exchange(body,*args):
                bundle=json.loads(json.loads(body)['messages'][1]['content']);return response(indexed_selection(bundle))
            with patch('advisor_groq.cloud_exchange',side_effect=exchange) as transport:
                report=run_validation(advisor,wait=wait)
            self.assertEqual(transport.call_count,7);self.assertFalse(report['real_inference_executed'])
            self.assertEqual(report['mode'],'simulated-contract');self.assertFalse(report['quality_validated'])
            for case in report['cases']:
                self.assertTrue(case['diagnosis_matches_scanner']);self.assertTrue(case['draft_grounded_or_abstained']);self.assertTrue(case['no_repair_authority'])
            self.assertEqual(len([x for x in report['cases'] if x['language']=='ro']),1)
            self.assertNotIn(KEY,json.dumps(report))
    def test_live_mode_rejects_non_cloud_simulation_provider(self):
        with tempfile.TemporaryDirectory() as root:
            advisor=ContextualAdvisor(Path(root)/'ledger.sqlite',SimulatedProvider())
            with self.assertRaises(ValueError):run_validation(advisor,live=True,wait=lambda _:None)
    def test_notebook_contains_no_executed_outputs_credentials_or_paid_runtime(self):
        notebook=json.loads(Path('notebooks/validate_cloud_advisor.ipynb').read_text())
        for cell in notebook['cells']:
            if cell['cell_type']=='code':
                self.assertEqual(cell['outputs'],[]);self.assertIsNone(cell['execution_count'])
                compile(''.join(cell['source']),'colab-cell','exec')
        text=json.dumps(notebook)
        self.assertIn('userdata.get',text);self.assertNotIn(KEY,text)
        self.assertNotIn('accelerator',notebook['metadata'])
