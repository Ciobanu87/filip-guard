import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from advisor_groq import GroqFreeProvider,build_payload
from contextual_advisor import ContextualAdvisor
from validate_cloud_advisor import run_probe,probe_request_metrics
from test_advisor_groq import KEY,response,indexed_selection
from test_contextual_advisor import ROWS,CONTEXT,SCOPE

class SingleProbeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.now=100.0
        self.engine=ContextualAdvisor(Path(self.temp.name)/'ledger.sqlite',GroqFreeProvider(lambda:KEY,free_plan_confirmed=True,data_consent=True),max_output_tokens=256,clock=lambda:self.now)
    def valid(self,body,*args):
        request=json.loads(body);self.assertEqual(request['max_completion_tokens'],256)
        return response(indexed_selection(json.loads(request['messages'][1]['content'])))
    def test_probe_is_one_case_one_attempt_not_seven_and_preserves_checked_evidence(self):
        with patch('advisor_groq.cloud_exchange',side_effect=self.valid) as call:report=run_probe(self.engine)
        call.assert_called_once();self.assertEqual(len(report['cases']),1)
        self.assertEqual(report['attempted_cases'],1);self.assertEqual(report['accepted_ai_cases'],1)
        self.assertFalse(report['real_inference_executed']);self.assertFalse(report['ready_for_full_evaluation'])
        self.assertEqual(report['planned_request_metrics']['max_output_tokens'],256)
        self.assertNotIn(KEY,json.dumps(report))
    def test_legacy_cooldown_causes_zero_calls_and_reports_eligibility_without_refund(self):
        with self.engine.db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS advisor_budget (day INTEGER PRIMARY KEY,calls INTEGER NOT NULL)')
            db.execute('INSERT INTO advisor_budget VALUES (0,7)')
            db.execute('INSERT INTO advisor_requests VALUES (?,?,?,?,?,?,?)',(SCOPE,'legacy',100,700,0,'failed',json.dumps({'diagnostic':{'http_status':429,'retry_after_seconds':120}})))
        self.now=150
        with patch('advisor_groq.cloud_exchange') as call:report=run_probe(self.engine)
        call.assert_not_called();self.assertEqual(report['attempted_cases'],0)
        self.assertEqual(report['cases'][0]['status'],'provider-cooldown')
        self.assertTrue(report['provider_expiry_confirmed']);self.assertIn('00:04:00',report['next_eligible_utc'])
        with self.engine.db() as db:self.assertEqual(db.execute('SELECT calls FROM advisor_budget WHERE day=0').fetchone()[0],7)
    def test_cached_success_is_not_presented_as_a_new_real_call(self):
        with patch('advisor_groq.cloud_exchange',side_effect=self.valid) as call:
            run_probe(self.engine);report=run_probe(self.engine)
        call.assert_called_once();self.assertEqual(report['attempted_cases'],0)
        self.assertEqual(report['new_provider_responses'],0);self.assertFalse(report['real_inference_executed'])
        self.assertEqual(report['cases'][0]['cache_origin'],'validated-success')
    def test_payload_compaction_keeps_data_and_schema_unchanged(self):
        messages=[{'role':'user','content':'Dovezi în română.'}];schema={'type':'object','properties':{'answer':{'type':'boolean'}}}
        body,metrics=build_payload(messages,schema,max_output_tokens=256);payload=json.loads(body)
        self.assertEqual(payload['messages'],messages);self.assertEqual(payload['response_format']['json_schema']['schema'],schema)
        self.assertLess(len(body),len(json.dumps(payload,ensure_ascii=False).encode()))
        self.assertIn('heuristic',metrics['token_estimate_method']);self.assertLess(probe_request_metrics()['request_bytes'],2500)
    def test_probe_does_not_silently_use_large_batch_output_reservation(self):
        self.engine.tokens=1200
        with self.assertRaises(ValueError):run_probe(self.engine)
