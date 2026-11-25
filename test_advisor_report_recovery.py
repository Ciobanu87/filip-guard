import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from advisor_report_recovery import recover_reports, write_recovery
from advisor_quality_evaluation import quality_cases
from contextual_advisor import configured_advisor


def fixture_report():
    events=[]
    for spec in quality_cases():
        events.append({'case':spec['name'],'status':'model-assisted',
            'response_contract':'indexed-evidence-v3','selection_validated':True,
            'draft_grounded_or_abstained':True,'no_repair_authority':True,
            'diagnosis_matches_scanner':True,'rendered_language':spec['language'],
            'selected_evidence':[{'text':x} for x in spec['expected_evidence']],
            'review_sample':{'draft':None,'missing_information':
                [] if spec.get('contexts') or spec.get('text') else ['content_unavailable']}})
    return {'mode':'live-cloud','model':'qwen/qwen3.8-27b',
            'repository_revision':'a'*40,'cases':events}


class ReportRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)
    def save(self,report,name='report.json'):
        p=self.root/name;p.write_text(json.dumps(report));return p
    def test_all_nine_recovered_without_ledger_or_network_or_budget(self):
        source=self.save(fixture_report())
        with patch('advisor_groq.cloud_exchange',side_effect=AssertionError('No network')):
            report=recover_reports([source])
        self.assertEqual(report['accepted_case_count'],9)
        self.assertTrue(report['all_nine_fixture_results_preserved'])
        self.assertIsNone(report['remaining_api_budget'])
        self.assertFalse(report['ledger_reconstructed'])
        self.assertTrue(report['live_inference_blocked_pending_usage_reconciliation'])
        self.assertEqual(list(self.root.iterdir()),[source])
    def test_duplicate_reports_not_double_counted(self):
        a=self.save(fixture_report());b=self.save(fixture_report(),'copy.json')
        report=recover_reports([a,b,a])
        self.assertEqual(len(report['sources']),1)
        self.assertEqual(report['accepted_case_count'],9)
        self.assertTrue(all(len(x['source_sha256'])==1 for x in report['accepted_cases']))
    def test_cached_failures_and_claimed_aggregate_success_not_recovered(self):
        raw=fixture_report();raw['accepted_ai_cases']=999
        raw['cases'][0].update(status='cached-failure',diagnostic={'http_status':429})
        report=recover_reports([self.save(raw)])
        self.assertEqual(report['accepted_case_count'],8)
        self.assertNotIn('diagnostic',json.dumps(report))
    def test_evidence_language_authority_and_abstention_rechecked(self):
        raw=fixture_report()
        raw['cases'][0]['selected_evidence']=[{'text':'unrelated'}]
        raw['cases'][1]['rendered_language']='wrong'
        raw['cases'][2]['no_repair_authority']=1
        next(x for x in raw['cases'] if x['case']=='heading-context-en')['review_sample']['draft']='unproven'
        self.assertEqual(recover_reports([self.save(raw)])['accepted_case_count'],5)
    def test_duplicate_case_names_and_json_keys_rejected(self):
        raw=fixture_report();raw['cases'].append(copy.deepcopy(raw['cases'][0]))
        with self.assertRaises(ValueError):recover_reports([self.save(raw)])
        p=self.root/'bad.json';p.write_text('{"cases":[],"cases":[]}')
        with self.assertRaises(ValueError):recover_reports([p])
    def test_invalid_input_and_symlink_rejected(self):
        for text in ('[]','NaN','{}'):
            p=self.root/'bad.json';p.write_text(text)
            with self.assertRaises(ValueError):recover_reports([p])
        source=self.save(fixture_report());link=self.root/'link';link.symlink_to(source)
        with self.assertRaises(ValueError):recover_reports([link])
    def test_exclusive_private_output_and_no_report_text_or_usage_export(self):
        raw=fixture_report();raw['api_key']='secret-do-not-export'
        raw['usage']={'total_tokens':123};raw['cases'][0]['review_sample']['reason']='secret-do-not-export'
        report=recover_reports([self.save(raw)]);out=self.root/'recovery.json'
        write_recovery(report,out)
        self.assertEqual(out.stat().st_mode & 0o777,0o600)
        self.assertNotIn('secret-do-not-export',out.read_text())
        self.assertNotIn('total_tokens',out.read_text())
        with self.assertRaises(FileExistsError):write_recovery(report,out)
    def test_runtime_missing_or_invalid_ledger_never_creates_budget(self):
        for exists in (False,True):
            path=self.root/('invalid.sqlite' if exists else 'missing.sqlite')
            if exists:path.write_bytes(b'not a database')
            env={'FG_AI_AUTHORIZED':'1','FG_AI_PROVIDER':'ollama-local','FG_AI_LEDGER_DB':str(path)}
            with patch.dict(os.environ,env,clear=True),self.assertRaises(ValueError):configured_advisor()
            self.assertEqual(path.exists(),exists)
            if exists:self.assertEqual(path.read_bytes(),b'not a database')


if __name__=='__main__':unittest.main()
