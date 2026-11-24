import unittest
from unittest.mock import Mock,patch
from streamlit.testing.v1 import AppTest
import test_guard_application as fixtures
from guard_assets import GuardAssetDirectory
from monitoring_service import MonitoringService
from guard_module_scan import GuardModuleScan


class GuardModuleUITests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.UnifiedFlowTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.reader=Mock();self.directory=GuardAssetDirectory(self.f.sites,reader=self.reader)
        self.monitor=MonitoringService(self.directory,self.f.root/'new-monitor.sqlite',scanner=self.f.public_scan,
            module_runner=lambda settings,**kw:GuardModuleScan(settings,min_gap=0,**kw))
        for patcher in (patch('guard_application_ui.configured_guard_application',return_value=None),
                        patch('monitoring_ui.configured_monitoring',return_value=self.monitor),
                        patch.dict('os.environ',{'FG_CUSTOMER_AUTH_DB':self.f.auth.path})):
            patcher.start();self.addCleanup(patcher.stop)
        self.at=AppTest.from_file('app.py',default_timeout=30).run()
    def text(self,label,value):next(x for x in self.at.text_input if x.label==label).set_value(value)
    def click(self,label):
        next(x for x in self.at.button if x.label==label).click();self.at.run()
        self.assertFalse(list(self.at.exception))
    def login(self,name='alice',password='Alice-unified-password'):
        self.text('Account username',name);self.text('Account password',password);self.click('Sign in')

    def test_nonwordpress_api_proof_configuration_worker_history_and_alerts_from_main_ui(self):
        self.login();self.text('Resource HTTPS origin','https://service.example.com')
        next(x for x in self.at.selectbox if x.label=='Resource type').set_value('api')
        self.click('Prepare domain verification')
        proof=self.at.session_state['fg_customer_guard_pending_proof'];self.reader.return_value=(200,'text/plain',proof['token'].encode())
        self.click('Verify domain control');site_id=self.at.session_state['fg_customer_monitor_site']
        self.assertEqual(self.monitor.module_settings(self.at.session_state['fg_customer_session'],site_id)['api']['paths'],['/'])
        next(x for x in self.at.text_area if x.label=='Public endpoint paths — one per line').set_value('/health')
        next(x for x in self.at.checkbox if x.label=='Require a JSON object').set_value(True)
        self.text('Required public JSON keys — optional','status');self.text('Health status field — optional','status')
        self.text('Expected health status value — optional','ok');self.click('Save guard modules')
        next(x for x in self.at.checkbox if x.label=='Enable periodic monitoring').set_value(True)
        self.click('Save monitoring settings')
        raw=b'HTTP/1.1 503 Unavailable\r\nContent-Type: application/json\r\nContent-Length: 2\r\n\r\n{}'
        with patch('guard_network._https_request_exchange',return_value=raw):result=self.monitor.run_once()
        self.assertEqual(result['new'],1);self.assertFalse(result['repairs_authorized'])
        self.at.run();self.assertFalse(list(self.at.exception))
        session=self.at.session_state['fg_customer_session']
        self.assertTrue(self.monitor.history(session,site_id)[0]['report']['module_checks'])
        self.assertTrue(self.monitor.notifications(session))
        self.assertFalse(any(x.label=='Approve and apply test change' for x in self.at.button))
        self.click('Sign out');self.login('bob','Bob-unified-password')
        self.assertNotIn('https://service.example.com',[site['origin'] for site in self.directory.list_sites(self.at.session_state['fg_customer_session'])])
        self.assertFalse(any('service.example.com' in getattr(x,'value','') for x in self.at.text_input))

    def test_unsafe_guard_paths_are_rejected_without_network_or_disabling_website(self):
        self.login()
        next(x for x in self.at.checkbox if x.label=='Enable API & App Guard').set_value(True)
        next(x for x in self.at.text_area if x.label=='Public endpoint paths — one per line').set_value('/checkout?pay=1')
        with patch('guard_network._https_request_exchange') as exchange:self.click('Save guard modules')
        exchange.assert_not_called();self.assertTrue(any('Guard settings are invalid' in x.value for x in self.at.error))
        self.assertEqual(self.monitor.module_settings(self.at.session_state['fg_customer_session'],self.f.site_a),{'website':True})
