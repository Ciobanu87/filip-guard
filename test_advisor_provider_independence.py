"""Provider contract portability only; no other real provider is enabled."""
import json
from pathlib import Path
import tempfile
import unittest
from advisor_diagnostics import AdvisorFailure
from contextual_advisor import ContextualAdvisor
from test_contextual_advisor import ROWS,CONTEXT,SCOPE,selection
from test_advisor_groq import indexed_selection


class GenericFixtureProvider:
    name='offline-provider-a';model='fixture-model'
    def __init__(self,limited=False):self.calls=0;self.limited=limited
    def generate(self,messages,schema,**bounds):
        self.calls+=1
        if self.limited:raise AdvisorFailure('http_error','http',http_status=429,quota={'retry_after_seconds':120,'quota_kind':'requests_per_minute'})
        return selection(json.loads(messages[1]['content']))


class IndexedFixtureProvider(GenericFixtureProvider):
    name='offline-provider-b';selection_contract='indexed-evidence-v3'
    def generate(self,messages,schema,**bounds):
        self.calls+=1;return indexed_selection(json.loads(messages[1]['content']))


class ProviderIndependenceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'ledger.sqlite'
    def test_generic_and_indexed_contracts_share_engine_without_groq(self):
        for provider in (GenericFixtureProvider(),IndexedFixtureProvider()):
            result=ContextualAdvisor(self.path,provider,clock=lambda:100).analyze(ROWS,CONTEXT,scope=SCOPE)
            self.assertEqual(result['status'],'model-assisted');self.assertEqual(provider.calls,1)
            self.assertTrue(all(not r['autofix'] and not r['root_cause_verified'] for r in result['recommendations']))
    def test_provider_change_does_not_reset_global_daily_budget(self):
        first=GenericFixtureProvider();second=IndexedFixtureProvider()
        ContextualAdvisor(self.path,first,daily_calls=1,clock=lambda:100).analyze(ROWS,CONTEXT,scope=SCOPE)
        result=ContextualAdvisor(self.path,second,daily_calls=1,clock=lambda:200).analyze(ROWS,CONTEXT,scope=SCOPE)
        self.assertEqual(result['status'],'daily-limit');self.assertEqual(second.calls,0)
    def test_generic_provider_cooldown_survives_restart_and_applies_across_tenants(self):
        provider=GenericFixtureProvider(limited=True)
        first=ContextualAdvisor(self.path,provider,clock=lambda:100).analyze(ROWS,CONTEXT,scope=SCOPE)
        self.assertEqual(first['status'],'provider-cooldown')
        result=ContextualAdvisor(self.path,provider,clock=lambda:101).analyze(ROWS,CONTEXT,scope='c'*32+':'+'d'*32)
        self.assertEqual(result['status'],'provider-cooldown');self.assertEqual(provider.calls,1)
    def test_cache_is_bound_to_provider_identity(self):
        first=GenericFixtureProvider();second=IndexedFixtureProvider()
        for provider in (first,second):ContextualAdvisor(self.path,provider,clock=lambda:100).analyze(ROWS,CONTEXT,scope=SCOPE)
        self.assertEqual((first.calls,second.calls),(1,1))
        with ContextualAdvisor(self.path,first).db() as db:self.assertEqual(db.execute('SELECT calls FROM advisor_budget WHERE day=0').fetchone()[0],2)

    def test_unrelated_adapter_does_not_inherit_legacy_429_from_another_provider(self):
        first=GenericFixtureProvider(limited=True)
        engine=ContextualAdvisor(self.path,first,clock=lambda:100)
        engine.analyze(ROWS,CONTEXT,scope=SCOPE)
        with engine.db() as db:db.execute("UPDATE advisor_requests SET state='failed'")
        second=IndexedFixtureProvider()
        result=ContextualAdvisor(self.path,second,clock=lambda:101).analyze(ROWS,CONTEXT,scope=SCOPE)
        self.assertEqual(result['status'],'model-assisted');self.assertEqual(second.calls,1)
        with engine.db() as db:self.assertEqual(db.execute('SELECT calls FROM advisor_budget WHERE day=0').fetchone()[0],2)
