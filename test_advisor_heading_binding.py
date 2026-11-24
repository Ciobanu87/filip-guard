"""Regression of schema-valid duplicate uncertainty and precise safe diagnostics."""
import copy
import json
import unittest
from unittest.mock import patch
from advisor_context import evidence_bundle
from advisor_selection_contract import build_schema, normalize
from contextual_advisor import FOCUS, MISSING, validate_selection, ContextualAdvisor
from advisor_diagnostics import AdvisorFailure
from advisor_language import render_language
from advisor_quality_evaluation import quality_cases, run_quality_evaluation
import test_advisor_quality_evaluation as quality_tests
from test_advisor_groq import indexed_selection


def heading_input():
    spec=next(c for c in quality_cases() if c['name']=='heading-context-en')
    url='https://synthetic-validation.test/'+spec['name']
    rows=[dict(page=url,http_status=200,title='Guide',meta_description='Installation guide overview',h1_count=2,images_missing_alt=0)]
    bundle,facts,base=evidence_bundle(rows,{url:spec['contexts']})
    payload=indexed_selection(bundle)
    payload['recommendations'][base[0]['finding_id']]['evidence_id']='p0e2'
    payload['recommendations'][base[0]['finding_id']]['include_draft']=False
    return bundle,facts,base,payload


class HeadingBindingTests(unittest.TestCase):
    def test_schema_and_guard_bound_uncertainty_and_deduplicate_legacy_known_values(self):
        bundle,facts,base,payload=heading_input()
        fields=build_schema(base,facts,MISSING)['properties']['recommendations']['properties']['f0']['properties']
        self.assertEqual(fields['missing_information']['maxItems'],3)
        payload['recommendations']['f0']['missing_information']=['audience_unknown']*5
        normalized=normalize(payload,base,facts,FOCUS)
        self.assertEqual(normalized['recommendations'][0]['missing_information'],['audience_unknown'])
        self.assertEqual(validate_selection(normalized,bundle,facts,base,'test')[0]['evidence'][0]['id'],'p0e2')

    def test_invalid_evidence_and_invalid_uncertainty_remain_rejected_with_distinct_details(self):
        bundle,facts,base,payload=heading_input()
        for field,value,detail in [('evidence_id','p9e0','evidence_identifier'),
                                  ('missing_information',['invented-secret-token'],'missing_information_value'),
                                  ('include_draft',True,'draft_flag')]:
            with self.subTest(field=field):
                candidate=copy.deepcopy(payload);candidate['recommendations']['f0'][field]=value
                with self.assertRaises(AdvisorFailure) as caught:normalize(candidate,base,facts,FOCUS)
                self.assertEqual(caught.exception.diagnostic['binding_reason'],detail)
                self.assertNotIn('invented-secret-token',str(caught.exception.diagnostic))

    def test_unbounded_legacy_uncertainty_is_rejected_not_silently_truncated(self):
        bundle,facts,base,payload=heading_input();payload['recommendations']['f0']['missing_information']=['audience_unknown']*33
        with self.assertRaises(AdvisorFailure) as caught:normalize(payload,base,facts,FOCUS)
        self.assertEqual(caught.exception.diagnostic['binding_reason'],'missing_information_size')

    def test_reviewed_rendering_corrects_existing_cached_semantics_without_model_call(self):
        item={'problem':'Missing meta description','source':'model-assisted','reason':'A useful description.',
              'solution':'Write a relevant description.','evidence':[{'text':'Home'}],
              'missing_information':['content_unavailable','image_purpose_unknown'], 'seo_draft':None}
        for language in ('en','ro'):
            result=render_language({'recommendations':[item]},language)['recommendations'][0]
            self.assertNotIn('image_purpose_unknown',result['missing_information'])
            self.assertNotIn('“Home”',result['solution'])
            self.assertIsNone(result['seo_draft'])
        self.assertIn('insufficient',render_language({'recommendations':[item]},'en')['recommendations'][0]['reason'])

    def test_legacy_heading_failure_retries_once_preserving_eight_successes_and_spent_budget(self):
        fixture=quality_tests.QualityContinuationTests();fixture.setUp()
        try:
            def first(body,*args):
                request=json.loads(body);bundle=json.loads(request['messages'][1]['content'])
                if any(f['problem']=='H1 structure needs review' for f in bundle['findings']):
                    from test_advisor_groq import response
                    payload=indexed_selection(bundle);payload['recommendations']['f0']['evidence_id']='p9e0'
                    return response(payload)
                return fixture.valid(body,*args)
            with patch('advisor_groq.cloud_exchange',side_effect=first):
                report=run_quality_evaluation(fixture.engine,wait=fixture.wait)
            self.assertEqual(report['accepted_ai_cases'],8)
            # Emulate the owner's old generic failure; keep all budget rows intact.
            with fixture.engine.db() as db:
                row=db.execute("SELECT scope,request_hash,result FROM advisor_requests WHERE state='failed'").fetchone()
                result=json.loads(row[2]);result.pop('selection_revision')
                db.execute('UPDATE advisor_requests SET result=?,expires=? WHERE scope=? AND request_hash=?',
                           (json.dumps(result),fixture.now+600,row[0],row[1]))
            fixture.now+=61
            with patch('advisor_groq.cloud_exchange',side_effect=fixture.valid) as api:
                resumed=run_quality_evaluation(fixture.engine,wait=fixture.wait)
            self.assertEqual(api.call_count,1)
            self.assertEqual(resumed['completed_before_this_run'],8)
            self.assertEqual(resumed['accepted_ai_cases'],9)
            with fixture.engine.db() as db:self.assertEqual(db.execute('SELECT SUM(calls) FROM advisor_budget').fetchone()[0],10)
        finally:fixture.temp.cleanup()

    def test_new_binding_failure_remains_cached_without_automatic_retry(self):
        fixture=quality_tests.QualityContinuationTests();fixture.setUp()
        try:
            def invalid_heading(body,*args):
                request=json.loads(body);bundle=json.loads(request['messages'][1]['content'])
                if any(f['problem']=='H1 structure needs review' for f in bundle['findings']):
                    from test_advisor_groq import response
                    payload=indexed_selection(bundle);payload['recommendations']['f0']['evidence_id']='p9e0'
                    return response(payload)
                return fixture.valid(body,*args)
            with patch('advisor_groq.cloud_exchange',side_effect=invalid_heading):
                first=run_quality_evaluation(fixture.engine,wait=fixture.wait)
            self.assertEqual(first['accepted_ai_cases'],8)
            fixture.now+=61
            with patch('advisor_groq.cloud_exchange') as api:
                again=run_quality_evaluation(fixture.engine,wait=fixture.wait)
            api.assert_not_called()
            heading=next(c for c in again['cases'] if c['case']=='heading-context-en')
            self.assertEqual(heading['status'],'cached-failure')
            self.assertEqual(heading['diagnostic']['binding_reason'],'evidence_identifier')
        finally:fixture.temp.cleanup()
