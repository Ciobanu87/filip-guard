import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from advisor_diagnostics import AdvisorFailure
from advisor_groq import GroqFreeProvider
from contextual_advisor import ContextualAdvisor
from advisor_quota import quota_metadata,duration
from test_advisor_groq import KEY,response,indexed_selection
from test_contextual_advisor import ROWS,CONTEXT,SCOPE

class ProviderCooldownTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.path=Path(self.temp.name)/'ledger.sqlite'
        self.now=100.0;self.provider=GroqFreeProvider(lambda:KEY,free_plan_confirmed=True,data_consent=True)
        self.engine=ContextualAdvisor(self.path,self.provider,clock=lambda:self.now)
    def valid(self,body,*args):return response(indexed_selection(json.loads(json.loads(body)['messages'][1]['content'])))
    def calls(self):
        with self.engine.db() as db:return db.execute('SELECT calls FROM advisor_budget WHERE day=0').fetchone()[0]
    def test_known_429_blocks_all_scopes_until_expiry_then_same_input_can_retry_once(self):
        error=AdvisorFailure('http_error','http',http_status=429,retry_after=120,provider_code='rate_limit_exceeded',provider_type='tokens')
        with patch('advisor_groq.cloud_exchange',side_effect=error) as exchange:
            first=self.engine.analyze(ROWS,CONTEXT,scope=SCOPE)
            self.assertEqual(first['status'],'provider-cooldown');self.assertEqual(first['cache_origin'],'fresh-provider-limit')
            self.assertEqual(first['cooldown']['eligible_at'],220)
            self.now=219
            reopened=ContextualAdvisor(self.path,self.provider,clock=lambda:self.now)
            second=reopened.analyze(ROWS,CONTEXT,scope='c'*32+':'+'d'*32)
            self.assertEqual(second['status'],'provider-cooldown');self.assertEqual(exchange.call_count,1)
            self.assertEqual(self.calls(),1)
        self.now=220
        with patch('advisor_groq.cloud_exchange',side_effect=self.valid) as exchange:
            self.assertEqual(self.engine.analyze(ROWS,CONTEXT,scope=SCOPE)['status'],'model-assisted');exchange.assert_called_once()
        self.assertEqual(self.calls(),2)
    def test_legacy_429_is_migrated_without_erasing_budget_or_becoming_cached_failure(self):
        diagnostic={'stage':'http','code':'http_error','http_status':429,'retry_after_seconds':120}
        with self.engine.db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS advisor_budget (day INTEGER PRIMARY KEY,calls INTEGER NOT NULL)')
            db.execute('INSERT INTO advisor_budget VALUES (0,7)')
            db.execute('INSERT INTO advisor_requests VALUES (?,?,?,?,?,?,?)',(SCOPE,'legacy',100,700,0,'failed',json.dumps({'diagnostic':diagnostic})))
        self.now=150
        with patch('advisor_groq.cloud_exchange') as exchange:
            result=self.engine.analyze(ROWS,CONTEXT,scope=SCOPE)
        self.assertEqual(result['status'],'provider-cooldown');exchange.assert_not_called();self.assertEqual(self.calls(),7)
        self.now=240
        with patch('advisor_groq.cloud_exchange',side_effect=self.valid):self.assertEqual(self.engine.analyze(ROWS,CONTEXT,scope=SCOPE)['status'],'model-assisted')
        self.assertEqual(self.calls(),8)
    def test_unknown_legacy_expiry_is_conservative_not_presented_as_provider_reset(self):
        with self.engine.db() as db:
            db.execute('INSERT INTO advisor_requests VALUES (?,?,?,?,?,?,?)',(SCOPE,'legacy',100,700,0,'failed',json.dumps({'diagnostic':{'http_status':429}})))
        self.now=701
        with patch('advisor_groq.cloud_exchange') as exchange:result=self.engine.analyze(ROWS,CONTEXT,scope=SCOPE)
        exchange.assert_not_called();self.assertEqual(result['status'],'provider-cooldown')
        self.assertFalse(result['cooldown']['provider_expiry_confirmed']);self.assertEqual(result['cooldown']['eligible_at'],86520)
    def test_semantic_failures_remain_request_scoped_and_cached(self):
        with patch('advisor_groq.cloud_exchange',return_value=response({'recommendations':{}})) as exchange:
            first=self.engine.analyze(ROWS,CONTEXT,scope=SCOPE)
            second=self.engine.analyze(ROWS,CONTEXT,scope=SCOPE)
        self.assertEqual(first['status'],'model-unavailable-or-invalid');self.assertEqual(second['status'],'cached-failure')
        self.assertEqual(second['cache_origin'],'persistent-validation-failure');exchange.assert_called_once()
    def test_daily_budget_is_not_refunded_by_cooldown_expiry(self):
        self.engine.daily_calls=1
        with patch('advisor_groq.cloud_exchange',side_effect=AdvisorFailure('http_error','http',http_status=429,retry_after=61)):
            self.engine.analyze(ROWS,CONTEXT,scope=SCOPE)
        self.now=161
        with patch('advisor_groq.cloud_exchange') as exchange:result=self.engine.analyze(ROWS,CONTEXT,scope=SCOPE)
        self.assertEqual(result['status'],'daily-limit');exchange.assert_not_called();self.assertEqual(self.calls(),1)
    def test_token_daily_limit_is_not_shortened_to_minute_reset_and_raw_messages_are_not_saved(self):
        headers=[('x-ratelimit-reset-tokens','7.66s'),('x-ratelimit-limit-tokens','8000')]
        quota=quota_metadata(headers,{'message':'tokens per day (TPD). Limit 200000. '+KEY},now=100)
        self.assertEqual(quota['quota_kind'],'tokens_per_day');self.assertNotIn('retry_after_seconds',quota)
        self.assertNotIn(KEY,json.dumps(quota))
        quota=quota_metadata(headers,{'message':'tokens per minute (TPM)'},now=100)
        self.assertEqual(quota['retry_after_seconds'],7.66)
    def test_retry_after_longer_than_hour_and_duration_formats_are_preserved(self):
        quota=quota_metadata([('retry-after','7200')],now=100)
        self.assertEqual(quota['retry_after_seconds'],7200)
        self.assertEqual(duration('1h2m3.5s'),3723.5)
        self.assertIsNone(duration(KEY))
