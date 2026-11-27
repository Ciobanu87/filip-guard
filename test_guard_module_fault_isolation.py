import unittest
from unittest.mock import patch
from guard_module_contract import Check
from guard_module_scan import GuardModuleScan
from monitoring_scan import MonitoringReport,MonitoringCancelled

ORIGIN='https://example.com'
SETTINGS={'website':True,'commerce':{'paths':['/product']},'api':{'paths':['/health']},'infrastructure':{}}


def check(module,code='status',status='pass'):
    return Check(module,code,ORIGIN+'/health',status,'Observed condition','Review the published response')


class ModuleFaultIsolationTests(unittest.TestCase):
    def scan(self,registry,clock=None):
        website=lambda *a,**k:MonitoringReport((),(),(),(),(('page',ORIGIN),),True,0)
        scanner=GuardModuleScan(SETTINGS,website=website,network_factory=lambda *a,**k:object(),min_gap=0)
        with patch.dict('guard_module_scan.REGISTRY',registry,clear=True):return scanner(ORIGIN)
    def test_failed_module_does_not_discard_other_verified_modules(self):
        def broken(*args):raise ValueError('private internal detail')
        result=self.scan({'commerce':broken,'api':lambda *a:[check('api')],'infrastructure':lambda *a:[check('infrastructure','dns')]})
        self.assertFalse(result.complete)
        self.assertEqual(len(result.module_checks),2)
        self.assertIn(('api:status',ORIGIN+'/health'),result.scope)
        self.assertNotIn('private internal detail',str(result))
    def test_mislabeled_module_result_cannot_resolve_another_module(self):
        result=self.scan({'commerce':lambda *a:[check('api')],'api':lambda *a:[check('api','json-contract')]})
        self.assertFalse(result.complete)
        self.assertNotIn(('commerce:status',ORIGIN+'/health'),result.scope)
        self.assertEqual(len(result.module_checks),1)
    def test_authorization_cancellation_is_never_swallowed(self):
        def cancelled(*args):raise MonitoringCancelled()
        with self.assertRaises(MonitoringCancelled):self.scan({'commerce':cancelled})
    def test_late_result_is_unverified_without_losing_earlier_results(self):
        now=[0.0]
        def late(*args):
            now[0]=100.0
            yield check('api')
        with patch('guard_module_scan.time.monotonic',side_effect=lambda:now[0]):
            result=self.scan({'commerce':lambda *a:[check('commerce')],'api':late})
        self.assertFalse(result.complete)
        self.assertIn(('commerce:status',ORIGIN+'/health'),result.scope)
        self.assertNotIn(('api:status',ORIGIN+'/health'),result.scope)

    def test_late_website_result_cannot_contribute_verified_resolution_scope(self):
        now=[0.0]
        def website(*args,**kwargs):
            kwargs['before_request']();now[0]=100.0
            return MonitoringReport((),(),(),(),(('page',ORIGIN),),True,1)
        scanner=GuardModuleScan(SETTINGS,website=website,network_factory=lambda *a,**k:object(),min_gap=0)
        with patch('guard_module_scan.time.monotonic',side_effect=lambda:now[0]),patch.dict('guard_module_scan.REGISTRY',{},clear=True):
            result=scanner(ORIGIN)
        self.assertFalse(result.complete);self.assertEqual(result.scope,())
        self.assertEqual(result.requests,1) # Spent reservations are never refunded.
