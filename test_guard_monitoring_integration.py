import json
import unittest
from unittest.mock import patch
import test_monitoring_service as fixtures
from monitoring_service import MonitoringService,LeaseLost
from guard_module_scan import GuardModuleScan


class GuardMonitoringTests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.MonitoringServiceTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.service=MonitoringService(self.f.directory,self.f.path,scanner=self.f.scanner,
            module_runner=lambda settings,**kw:GuardModuleScan(settings,min_gap=0,**kw))
        self.settings={'website':False,'api':{'paths':['/health'],'required_keys':['status'],'json_equals':{'status':'ok'}}}

    def wire(self,body):
        return b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: '+str(len(body)).encode()+b'\r\n\r\n'+body

    def test_owner_isolation_and_settings_persist_without_changing_website_defaults(self):
        self.assertEqual(self.service.module_settings(self.f.a,self.f.site_a,now=100),{'website':True})
        with self.assertRaises(PermissionError):self.service.configure_modules(self.f.b,self.f.site_a,self.settings,now=100)
        self.service.configure_modules(self.f.a,self.f.site_a,self.settings,now=100)
        other=MonitoringService(self.f.directory,self.f.path)
        self.assertEqual(other.module_settings(self.f.a,self.f.site_a,now=100)['api']['paths'],['/health'])
        self.assertEqual(other.module_settings(self.f.b,self.f.site_b,now=100),{'website':True})

    def test_module_results_feed_existing_history_alerts_and_resolution_without_ai_or_repairs(self):
        self.service.configure_modules(self.f.a,self.f.site_a,self.settings,now=100);self.f.enable()
        with patch('guard_network._https_request_exchange',return_value=self.wire(b'{"status":"error"}')):
            failed=self.service.run_once(now=100)
        self.assertEqual(failed['new'],1);self.assertFalse(failed['repairs_authorized'])
        self.assertTrue(self.service.notifications(self.f.a,now=101))
        with patch('guard_network._https_request_exchange',return_value=self.wire(b'{"status":"ok"}')):
            recovered=self.service.run_once(now=1000)
        self.assertEqual(recovered['resolved'],1)
        self.f.refresh_session(self.f.a,1001);self.f.refresh_session(self.f.b,1001)
        history=self.service.history(self.f.a,self.f.site_a,now=1001)
        self.assertEqual(len(history),2);self.assertTrue(history[0]['report']['module_checks'])
        self.assertEqual(self.f.scanner.calls,[])
        self.assertEqual(self.service.notifications(self.f.b,now=1001),[])

    def test_failed_transport_preserves_previous_issue_and_never_claims_resolution(self):
        self.service.configure_modules(self.f.a,self.f.site_a,self.settings,now=100);self.f.enable()
        with patch('guard_network._https_request_exchange',return_value=self.wire(b'{"status":"error"}')):self.service.run_once(now=100)
        with patch('guard_network._https_request_exchange',side_effect=OSError('private failure')):
            result=self.service.run_once(now=1000)
        self.assertEqual(result['status'],'partial');self.assertEqual(result['resolved'],0)
        self.f.refresh_session(self.f.a,1001)
        self.assertTrue(self.service.snapshot(self.f.a,self.f.site_a,now=1001)['findings'])
        self.assertNotIn('private failure',json.dumps(self.service.notifications(self.f.a,now=1001)))

    def test_config_change_fences_running_job_without_resetting_due_or_spent_requests(self):
        self.f.enable();job=self.service.claim(now=100)
        self.assertEqual(self.service.reserve_request(job,now=100),0)
        due=self.service.snapshot(self.f.a,self.f.site_a,now=100)['schedule']['next_due']
        self.service.configure_modules(self.f.a,self.f.site_a,self.settings,now=100)
        with self.assertRaises(LeaseLost):self.service.checkpoint(job,now=100)
        self.assertGreaterEqual(self.service.snapshot(self.f.a,self.f.site_a,now=100)['schedule']['next_due'],due+900)
        self.assertIsNone(self.service.claim(now=101))
        self.assertIsNotNone(self.service.claim(now=1000))
        with self.service.db() as db:self.assertEqual(db.execute('SELECT requests FROM monitor_runs WHERE run_id=?',(job['run_id'],)).fetchone()[0],1)

    def test_four_modules_share_history_resolution_and_isolation_without_ai(self):
        settings={'website':True,'commerce':{'paths':['/product'],'require_product':True,'expected_currency':'EUR'},
                  'api':{'paths':['/health'],'json_equals':{'status':'ok'}},'infrastructure':{}}
        self.service.configure_modules(self.f.a,self.f.site_a,settings,now=100)
        self.service.configure(self.f.a,self.f.site_a,enabled=True,interval_seconds=900,page_limit=1,max_requests=10,now=100)
        healthy=[False]
        original_reserve=self.service.reserve_request;slots={}
        def reserve(job,*,now=None):
            # Advance deterministic request slots while retaining the real one-second limiter.
            slots[now]=slots.get(now,now)+1
            return original_reserve(job,now=slots[now])
        def exchange(host,path,*args,**kwargs):
            if path=='/product':
                body=(b'<script type="application/ld+json">{"@type":"Product","offers":{"price":"10","priceCurrency":"EUR"}}</script>' if healthy[0] else b'<h1>Product</h1>')
                kind=b'text/html'
            else:
                body=b'{"status":"ok","token":"do-not-persist"}' if healthy[0] else b'{"status":"error","token":"do-not-persist"}'
                kind=b'application/json'
            return b'HTTP/1.1 200 OK\r\nContent-Type: '+kind+b'\r\nContent-Length: '+str(len(body)).encode()+b'\r\n\r\n'+body
        with patch.object(self.service,'reserve_request',side_effect=reserve), \
             patch('guard_network._https_request_exchange',side_effect=exchange), \
             patch('guard_network.GuardNetwork.dns',return_value=['93.184.216.34']), \
             patch('guard_network.GuardNetwork.certificate_expiry',return_value=4102444800), \
             patch('contextual_advisor.configured_advisor',side_effect=AssertionError('Monitoring cannot request AI')):
            failed=self.service.run_once(now=100)
            self.assertEqual(failed['new'],3)
            healthy[0]=True;self.f.scanner.missing=False
            restored=self.service.run_once(now=1000)
            self.assertEqual(restored['resolved'],3)
        self.f.refresh_session(self.f.a,1001);self.f.refresh_session(self.f.b,1001)
        history=self.service.history(self.f.a,self.f.site_a,now=1001)
        self.assertEqual(len(history),2)
        report=history[0]['report']
        self.assertEqual({item['module'] for item in report['module_checks']},{'commerce','api','infrastructure'})
        self.assertTrue(report['rows'])
        self.assertNotIn('do-not-persist',json.dumps(history))
        self.assertEqual(self.service.notifications(self.f.b,now=1001),[])
        self.assertFalse(restored['repairs_authorized'])

    def test_unexpected_module_fault_preserves_prior_unresolved_issue(self):
        self.service.configure_modules(self.f.a,self.f.site_a,self.settings,now=100);self.f.enable()
        with patch('guard_network._https_request_exchange',return_value=self.wire(b'{"status":"error"}')):
            self.assertEqual(self.service.run_once(now=100)['new'],1)
        def broken(*args):raise RuntimeError('private provider response')
        with patch.dict('guard_module_scan.REGISTRY',{'api':broken},clear=True):
            result=self.service.run_once(now=1000)
        self.assertEqual(result['status'],'partial');self.assertEqual(result['resolved'],0)
        self.f.refresh_session(self.f.a,1001)
        self.assertTrue(self.service.snapshot(self.f.a,self.f.site_a,now=1001)['findings'])
        self.assertNotIn('private provider response',json.dumps(self.service.history(self.f.a,self.f.site_a,now=1001)))
