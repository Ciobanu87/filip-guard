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
