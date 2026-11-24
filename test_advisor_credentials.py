import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch
from advisor_credentials import SessionCredential,is_credential_failure
from advisor_diagnostics import AdvisorFailure
from advisor_groq import GroqFreeProvider
from contextual_advisor import ContextualAdvisor
from test_advisor_groq import KEY,response,indexed_selection
from test_contextual_advisor import ROWS,CONTEXT,SCOPE

class SessionCredentialTests(unittest.TestCase):
    def test_successful_colab_preflight_is_reused_without_later_ui_rpc(self):
        read=Mock(side_effect=[KEY,TimeoutError('sensitive message')])
        credential=SessionCredential.load(read)
        provider=GroqFreeProvider(credential,free_plan_confirmed=True,data_consent=True)
        with patch('advisor_groq.cloud_exchange',return_value=response()):
            for _ in range(3):provider.check_ready();provider.generate([],{})
        read.assert_called_once();self.assertNotIn(KEY,repr(credential));self.assertNotIn(KEY,str(credential))
        credential.close()
        with self.assertRaises(AdvisorFailure) as caught:credential()
        self.assertEqual(caught.exception.diagnostic['code'],'key_closed')
    def test_missing_denied_timeout_and_invalid_are_distinct_and_never_echo_values(self):
        for name,code in [('TimeoutException','key_access_timeout'),('NotebookAccessError','key_access_denied'),('SecretNotFoundError','key_not_found')]:
            error=type(name,(Exception,),{})(KEY)
            with self.assertRaises(AdvisorFailure) as caught:SessionCredential.load(Mock(side_effect=error))
            self.assertEqual(caught.exception.diagnostic['code'],code);self.assertNotIn(KEY,str(caught.exception))
        with self.assertRaises(AdvisorFailure) as caught:SessionCredential.load(lambda:'bad')
        self.assertEqual(caught.exception.diagnostic['code'],'key_invalid')
    def test_credential_failure_before_reservation_does_not_spend_budget_or_call_groq(self):
        with tempfile.TemporaryDirectory() as root:
            provider=GroqFreeProvider(Mock(side_effect=TimeoutError(KEY)),free_plan_confirmed=True,data_consent=True)
            engine=ContextualAdvisor(Path(root)/'ledger.sqlite',provider,clock=lambda:100)
            with patch('advisor_groq.cloud_exchange') as api:
                result=engine.analyze(ROWS,CONTEXT,scope=SCOPE)
            api.assert_not_called();self.assertEqual(result['status'],'credential-unavailable')
            with engine.db() as db:
                self.assertEqual(db.execute('SELECT calls FROM advisor_budget WHERE day=0').fetchone()[0],0)
                self.assertEqual(db.execute('SELECT count(*) FROM advisor_requests').fetchone()[0],0)
    def test_old_key_failure_is_not_replayed_after_access_recovers_and_budget_is_not_refunded(self):
        with tempfile.TemporaryDirectory() as root:
            provider=GroqFreeProvider(lambda:KEY,free_plan_confirmed=True,data_consent=True)
            engine=ContextualAdvisor(Path(root)/'ledger.sqlite',provider,clock=lambda:100)
            def valid(body,*args):return response(indexed_selection(json.loads(json.loads(body)['messages'][1]['content'])))
            with patch('advisor_groq.cloud_exchange',side_effect=valid):engine.analyze(ROWS,CONTEXT,scope=SCOPE)
            # Reconstruct the same-key cached input failure left by the old version.
            with engine.db() as db:
                db.execute("UPDATE advisor_requests SET state='failed',result=?,expires=1000",(json.dumps({'diagnostic':{'stage':'input','code':'key_unavailable'}}),))
            engine.clock=lambda:161
            with patch('advisor_groq.cloud_exchange',side_effect=valid) as api:
                result=engine.analyze(ROWS,CONTEXT,scope=SCOPE)
            self.assertEqual(result['status'],'model-assisted');api.assert_called_once()
            with engine.db() as db:self.assertEqual(db.execute('SELECT calls FROM advisor_budget WHERE day=0').fetchone()[0],2)
    def test_new_key_failure_is_not_stored_as_semantic_failure_or_retried_in_batch(self):
        from advisor_quality_evaluation import run_quality_evaluation
        with tempfile.TemporaryDirectory() as root:
            getter=Mock(side_effect=TimeoutError(KEY))
            provider=GroqFreeProvider(getter,free_plan_confirmed=True,data_consent=True)
            engine=ContextualAdvisor(Path(root)/'ledger.sqlite',provider,clock=lambda:100,max_output_tokens=256)
            report=run_quality_evaluation(engine,wait=lambda _:None)
        getter.assert_called_once();self.assertTrue(report['stopped_early']);self.assertEqual(report['attempted_cases'],0)
        self.assertEqual(report['cases'][0]['diagnostic']['code'],'key_access_timeout')
        self.assertNotIn(KEY,json.dumps(report))
