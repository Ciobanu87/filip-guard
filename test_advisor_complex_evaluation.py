import copy
import json
from pathlib import Path
import tempfile
import unittest
from advisor_complex_evaluation import complex_cases,oracle_selection,evaluate_selection,run_complex_evaluation
from advisor_context import evidence_bundle
from advisor_diagnostics import AdvisorFailure
from advisor_language import render_language
from advisor_selection_contract import normalize
from contextual_advisor import ContextualAdvisor,FOCUS,validate_selection,rule_result
from test_advisor_groq import indexed_selection


class ComplexAdvisorSafetyTests(unittest.TestCase):
    def setUp(self):self.cases=complex_cases();self.spec=self.cases[0]
    def test_new_cases_are_distinct_from_original_live_suite(self):
        names=[s['name'] for s in self.cases]
        self.assertEqual(len(names),len(set(names)))
        self.assertFalse(set(names)&{'documentation','nonprofit','international','insufficient','wordpress-post','injection','heading-context-en','image-caption-ro','sparse-context-en'})
    def test_simultaneous_findings_and_batch_limit_are_reported_honestly(self):
        report=evaluate_selection(self.spec,oracle_selection(self.spec))
        self.assertTrue(report['contract_accepted']);self.assertTrue(report['fixture_relevance_passed'])
        self.assertEqual((report['model_batch_findings'],report['all_rule_findings']),(8,12))
        self.assertEqual(report['provider_calls'],0);self.assertFalse(report['human_semantic_quality_validated'])
    def test_structural_acceptance_does_not_mislabel_irrelevant_evidence_as_quality(self):
        report=evaluate_selection(self.spec,oracle_selection(self.spec,irrelevant=True))
        self.assertTrue(report['contract_accepted']);self.assertFalse(report['fixture_relevance_passed'])
    def test_cross_page_evidence_is_rejected_in_simultaneous_batch(self):
        payload=oracle_selection(self.spec);payload['recommendations'][0]['evidence_ids']=['p1e0']
        self.assertFalse(evaluate_selection(self.spec,payload)['contract_accepted'])
    def test_duplicate_or_missing_finding_rejects_entire_batch(self):
        for mutate in ('duplicate','missing'):
            payload=oracle_selection(self.spec)
            if mutate=='duplicate':payload['recommendations'][1]=copy.deepcopy(payload['recommendations'][0])
            else:payload['recommendations'].pop()
            self.assertFalse(evaluate_selection(self.spec,payload)['contract_accepted'])
    def test_freeform_solution_or_execution_authority_cannot_enter_contract(self):
        for field,value in [('solution','Disable TLS certificate verification.'),('autofix',True),('root_cause','Database corruption proven')]:
            payload=oracle_selection(self.spec);payload['recommendations'][0][field]=value
            self.assertFalse(evaluate_selection(self.spec,payload)['contract_accepted'])
    def test_downgrade_cannot_hide_high_priority_finding(self):
        payload=oracle_selection(self.spec);payload['recommendations'][0]['priority']='Low'
        self.assertFalse(evaluate_selection(self.spec,payload)['contract_accepted'])
    def test_partial_context_stays_unconfirmed_and_draftless(self):
        spec=self.cases[1];result=render_language(rule_result(spec['rows'],spec['contexts']))
        self.assertTrue(all('content_unavailable' in r['missing_information'] for r in result['recommendations']))
        self.assertTrue(all(r['seo_draft'] is None and not r['autofix'] and not r['root_cause_verified'] for r in result['recommendations']))
    def test_overflow_does_not_invent_missing_content(self):
        result=rule_result(self.spec['rows'],self.spec['contexts'])
        self.assertEqual(len(result['recommendations']),12)
        self.assertTrue(all(r['evidence'] for r in result['recommendations'][8:]))
        self.assertTrue(all('content_unavailable' not in r['missing_information'] for r in result['recommendations']))
    def test_observed_body_beyond_display_evidence_limit_is_not_called_missing(self):
        row=dict(self.spec['rows'][0],title='A descriptive title',meta_description='A descriptive summary')
        result=rule_result([row],{row['page']:['First short section.','Second short section.']})
        self.assertTrue(all('content_unavailable' not in r['missing_information'] for r in result['recommendations']))
    def test_known_dangerous_extractive_drafts_are_rejected_by_generic_guard(self):
        for spec in self.cases[2:]:
            bundle,facts,base=evidence_bundle(spec['rows'],spec['contexts']);payload=oracle_selection(spec)
            payload['recommendations'][0]['seo_draft']=spec['contexts'][spec['rows'][0]['page']][0]
            with self.subTest(case=spec['name']),self.assertRaises(AdvisorFailure):validate_selection(payload,bundle,facts,base,'simulated')
    def test_indexed_path_abstains_without_promoting_dangerous_excerpt(self):
        for spec in self.cases[2:]:
            bundle,facts,base=evidence_bundle(spec['rows'],spec['contexts']);payload=indexed_selection(bundle)
            for finding in payload['recommendations'].values():
                finding['evidence_id']=next(k for k,f in facts.items() if f['kind']=='content')
            payload['recommendations']['f0']['include_draft']=True
            result=validate_selection(normalize(payload,base,facts,FOCUS),bundle,facts,base,'simulated')
            self.assertTrue(all(r['seo_draft'] is None and not r['autofix'] for r in result))
    def test_historical_display_abstains_without_rewriting_original_or_new_inference(self):
        spec=self.cases[2];result=rule_result(spec['rows'],spec['contexts'])
        result['recommendations'][0]['seo_draft']=spec['contexts'][spec['rows'][0]['page']][0]
        original=copy.deepcopy(result)
        for language in ('en','ro'):
            displayed=render_language(result,language)
            self.assertIsNone(displayed['recommendations'][0]['seo_draft'])
            self.assertEqual(displayed['recommendations'][0]['draft_withheld_reason'],'unsafe-extractive-content')
        self.assertEqual(result,original)
    def test_engine_preserves_all_findings_and_only_one_simulated_batch(self):
        spec=self.spec
        class Provider:
            name='offline-complex-fixture';model='simulated';calls=0
            def generate(self,*args,**kwargs):self.calls+=1;return oracle_selection(spec)
        provider=Provider()
        with tempfile.TemporaryDirectory() as directory:
            engine=ContextualAdvisor(Path(directory)/'ledger.sqlite',provider)
            result=engine.analyze(spec['rows'],spec['contexts'],scope='a'*32+':'+'b'*32)
            self.assertEqual(len(result['recommendations']),12)
            self.assertEqual(sum(r['source']=='model-assisted' for r in result['recommendations']),8)
            self.assertEqual(sum(r['source']=='rules' for r in result['recommendations']),4)
            self.assertEqual(provider.calls,1)
            self.assertTrue(all(not r['autofix'] and not r['root_cause_verified'] for r in result['recommendations']))

    def test_risky_page_text_is_evidence_not_a_solution_or_review_instruction(self):
        for spec in self.cases[2:]:
            bundle,facts,base=evidence_bundle(spec['rows'],spec['contexts'])
            recommendations=validate_selection(oracle_selection(spec),bundle,facts,base,'simulated')
            raw=spec['contexts'][spec['rows'][0]['page']][0]
            for language in ('en','ro'):
                displayed=render_language({'status':'model-assisted','recommendations':recommendations},language)
                self.assertTrue(any(raw in e['text'] for r in displayed['recommendations'] for e in r['evidence']))
                for item in displayed['recommendations']:
                    self.assertNotIn(raw,item['solution'])
                    self.assertNotIn(raw,' '.join(item['review_steps']))

    def test_report_separates_positive_fixtures_from_six_adversarial_rejections(self):
        report=run_complex_evaluation()
        self.assertEqual(len(report['cases']),11)
        self.assertEqual(sum(case['contract_accepted'] for case in report['cases']),5)
        self.assertTrue(all(not case['contract_accepted'] for case in report['cases'][5:]))
        self.assertTrue(all(case['no_repairs_authorized'] for case in report['cases']))
        self.assertEqual(report['provider_calls'],0)
        self.assertEqual(report['original_live_cases_repeated'],0)
        self.assertFalse(report['human_semantic_quality_validated'])
