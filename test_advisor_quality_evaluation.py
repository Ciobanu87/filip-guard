import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from advisor_context import evidence_bundle
from advisor_selection_contract import normalize
from advisor_groq import GroqFreeProvider
from contextual_advisor import ContextualAdvisor
from advisor_quality_evaluation import quality_cases,run_quality_evaluation,observable_quality
from test_advisor_groq import KEY,response,indexed_selection

class QualityContinuationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.now=100.0
        self.engine=ContextualAdvisor(Path(self.temp.name)/'ledger.sqlite',GroqFreeProvider(lambda:KEY,free_plan_confirmed=True,data_consent=True),clock=lambda:self.now,max_output_tokens=256)
    def wait(self,seconds):self.assertEqual(seconds,61);self.now+=seconds
    def valid(self,body,*args):
        request=json.loads(body);bundle=json.loads(request['messages'][1]['content'])
        self.assertNotIn('expected_evidence',str(request));self.assertEqual(request['max_completion_tokens'],256)
        payload=indexed_selection(bundle)
        # Simulated oracle-guided selection is explicitly not model reasoning.
        for finding in bundle['findings']:
            page=next(p for p in bundle['pages'] if p['id']==finding['page_id'])
            substantive=[e for e in page['evidence'] if e['kind']=='content']
            if substantive:
                chosen=substantive[0]
                payload['recommendations'][finding['id']]['evidence_id']=chosen['id']
                payload['recommendations'][finding['id']]['include_draft']=finding['problem']=='Missing meta description'
        return response(payload)
    def test_remaining_cases_cover_en_ro_other_issues_and_do_not_repeat_craft(self):
        cases=quality_cases();self.assertEqual(len(cases),9);self.assertNotIn('craft',[c['name'] for c in cases])
        self.assertTrue(any(c['language']=='ro' and c['problem']=='Images missing ALT text' for c in cases))
        with patch('advisor_groq.cloud_exchange',side_effect=self.valid) as api:report=run_quality_evaluation(self.engine,wait=self.wait)
        self.assertEqual(api.call_count,9);self.assertEqual(report['accepted_ai_cases'],9)
        self.assertEqual(report['observable_quality_passes'],9);self.assertFalse(report['real_inference_executed']);self.assertFalse(report['quality_validated'])
        self.assertNotIn(KEY,json.dumps(report));self.assertFalse(report['oracle_sent_to_model'])
        self.assertTrue(all(x['quality_review']['human_relevance_score'] is None for x in report['cases']))
    def test_structurally_valid_but_irrelevant_evidence_does_not_pass_quality_gate(self):
        spec=next(x for x in quality_cases() if x['name']=='heading-context-en')
        event={'status':'model-assisted','selection_validated':True,'review_sample':{'draft':None,'missing_information':[]},
               'selected_evidence':[{'text':spec['contexts'][1]}],'draft_grounded_or_abstained':True,
               'rendered_language':'en','no_repair_authority':True,'diagnosis_matches_scanner':True}
        result=observable_quality(event,spec)
        self.assertFalse(result['observable_gates_passed']);self.assertFalse(result['checks']['fixture_relevant_evidence_selected'])
    def test_local_daily_budget_stops_without_making_remaining_calls_or_resetting_usage(self):
        self.engine.daily_calls=1
        with patch('advisor_groq.cloud_exchange',side_effect=self.valid) as api:report=run_quality_evaluation(self.engine,wait=self.wait)
        self.assertEqual(api.call_count,1);self.assertTrue(report['stopped_early'])
        self.assertTrue(any(x['status']=='not-run' for x in report['cases']))
        with self.engine.db() as db:self.assertEqual(db.execute('SELECT calls FROM advisor_budget').fetchone()[0],1)

    def test_three_completed_fixtures_survive_expiry_and_restart_only_six_calls_remain(self):
        from validate_cloud_advisor import run_validation
        with patch('advisor_groq.cloud_exchange',side_effect=self.valid) as api:
            first=run_validation(self.engine,wait=self.wait,case_specs=quality_cases()[:3])
        self.assertEqual(first['accepted_ai_cases'],3)
        self.now+=7200
        restarted=ContextualAdvisor(self.engine.path,self.engine.provider,clock=lambda:self.now,max_output_tokens=256)
        with patch('advisor_groq.cloud_exchange',side_effect=self.valid) as api:
            report=run_quality_evaluation(restarted,wait=self.wait)
        self.assertEqual(api.call_count,6)
        self.assertEqual(report['completed_before_this_run'],3)
        self.assertEqual(report['accepted_ai_cases'],9)
        self.assertEqual(report['planned_provider_calls_max'],6)
        self.assertTrue(all(not x['provider_request_attempted'] for x in report['cases'][:3]))
        self.assertEqual(report['observable_quality_passes'],9)
        with self.engine.db() as db:self.assertEqual(db.execute('SELECT SUM(calls) FROM advisor_budget').fetchone()[0],9)
        self.now+=7200
        with patch('advisor_groq.cloud_exchange') as api:
            again=run_quality_evaluation(restarted,wait=self.wait)
        api.assert_not_called()
        self.assertEqual(again['completed_before_this_run'],9)
        self.assertFalse(again['real_inference_executed'])

    def test_completed_fixture_replay_does_not_clear_provider_cooldown(self):
        from validate_cloud_advisor import run_validation
        with patch('advisor_groq.cloud_exchange',side_effect=self.valid):
            run_validation(self.engine,wait=self.wait,case_specs=quality_cases()[:3])
        self.now+=61
        from advisor_diagnostics import AdvisorFailure
        with patch('advisor_groq.cloud_exchange',side_effect=AdvisorFailure('http_error','http',http_status=429,retry_after=3600,provider_code='rate_limit_exceeded',provider_type='tokens')) as api:
            report=run_quality_evaluation(self.engine,wait=self.wait)
        self.assertEqual(api.call_count,1)
        self.assertEqual(report['completed_before_this_run'],3)
        self.assertTrue(report['stopped_early'])
        with patch('advisor_groq.cloud_exchange') as api:
            again=run_quality_evaluation(self.engine,wait=self.wait)
        api.assert_not_called()
        self.assertEqual(again['cases'][3]['status'],'provider-cooldown')
