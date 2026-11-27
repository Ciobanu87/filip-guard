import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from validate_complex_advisor import main,run_complex_validation
from contextual_advisor import ContextualAdvisor
from test_contextual_advisor import selection
import json


class SyntheticProvider:
    name='offline-complex-readiness';model='simulated';minimum_interval=0
    def __init__(self):self.calls=0;self.fail=False
    def generate(self,messages,*args,**kwargs):
        self.calls+=1
        if self.fail:raise RuntimeError('private provider detail')
        bundle=json.loads(messages[1]['content']);payload=selection(bundle)
        for finding,item in zip(bundle['findings'],payload['recommendations']):
            page=next(page for page in bundle['pages'] if page['id']==finding['page_id'])
            bodies=[fact for fact in page['evidence'] if fact['kind']=='content']
            if bodies:item['evidence_ids']=[bodies[0]['id']]
            item['seo_draft']=None
        return payload


class ComplexValidationReadinessTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.provider=SyntheticProvider()
        self.engine=ContextualAdvisor(self.root/'ledger.sqlite',self.provider)
    def test_default_does_not_load_configuration_or_read_keys(self):
        with patch('contextual_advisor.configured_advisor',side_effect=AssertionError('no provider')),patch('sys.stdout',new_callable=io.StringIO) as output:
            self.assertEqual(main([]),0)
        self.assertEqual(json.loads(output.getvalue())['status'],'approval-required')
        self.assertEqual(self.provider.calls,0)
    def test_recorded_cases_are_not_repeated_and_budget_is_preserved(self):
        receipts=self.root/'receipts'
        report=run_complex_validation(self.engine,authorized=True,directory=receipts)
        self.assertEqual(report['fresh_case_admissions'],5);self.assertEqual(self.provider.calls,5)
        again=run_complex_validation(self.engine,authorized=True,directory=receipts)
        self.assertEqual(again['fresh_case_admissions'],0);self.assertEqual(self.provider.calls,5)
        with self.engine.db() as db:self.assertEqual(db.execute('SELECT sum(calls) FROM advisor_budget').fetchone()[0],5)
        self.assertTrue(all(path.stat().st_mode&0o077==0 for path in receipts.iterdir()))
    def test_lost_result_after_attempt_is_held_without_retry(self):
        receipts=self.root/'receipts';receipts.mkdir(mode=0o700)
        (receipts/'simultaneous-overflow.attempt.json').write_text('{}')
        result=run_complex_validation(self.engine,authorized=True,directory=receipts)
        self.assertEqual(result['status'],'held-uncertain-validation-attempt');self.assertEqual(self.provider.calls,0)
    def test_invalid_response_stops_and_is_not_replayed(self):
        self.provider.fail=True;receipts=self.root/'receipts'
        result=run_complex_validation(self.engine,authorized=True,directory=receipts)
        self.assertEqual(result['status'],'held-validation-failure');self.assertEqual(self.provider.calls,1)
        again=run_complex_validation(self.engine,authorized=True,directory=receipts)
        self.assertEqual(again['status'],'held-previous-validation-failure');self.assertEqual(self.provider.calls,1)
        self.assertNotIn('private provider detail',json.dumps(again))

    def test_relevance_failure_stops_even_when_contract_is_accepted(self):
        from test_contextual_advisor import selection
        def irrelevant(messages,*args,**kwargs):
            self.provider.calls+=1
            return selection(json.loads(messages[1]['content']))
        self.provider.generate=irrelevant
        receipts=self.root/'receipts'
        result=run_complex_validation(self.engine,authorized=True,directory=receipts)
        self.assertEqual(result['status'],'held-validation-failure')
        self.assertTrue(result['cases'][0]['response_contract_validated'])
        self.assertFalse(result['cases'][0]['fixture_relevance_passed'])
        self.assertEqual(self.provider.calls,1)
        self.assertEqual(run_complex_validation(self.engine,authorized=True,directory=receipts)['status'],'held-previous-validation-failure')
        self.assertEqual(self.provider.calls,1)
