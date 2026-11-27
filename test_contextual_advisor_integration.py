from dataclasses import replace
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
import test_guard_application as fixture
from test_contextual_advisor import SimulatedProvider
from contextual_advisor import ContextualAdvisor
from monitoring_scan import make_report

class AuthenticatedAdvisorIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.f=fixture.UnifiedFlowTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.provider=SimulatedProvider();self.engine=ContextualAdvisor(self.f.root/'model-ledger.sqlite',self.provider)
        original=self.f.application.scanner
        def scanner(origin,**kwargs):
            report=original(origin,**kwargs)
            rows=[{**r,'meta_description':''} for r in report.rows]
            return make_report(rows,report.broken,[],report.requests,link_sources={origin+'/missing-destination/':{origin+'/source/'}},
                page_context={r['page']:['Handmade oak dining tables built in our workshop.'] for r in rows})
        self.f.application.scanner=scanner
        self.scan=self.f.application.scan(self.f.a,self.f.site_a,start_url=self.f.origins[0]+'/source/',page_limit=1)
    def test_advice_is_explicit_owner_scoped_persistent_and_not_repair_authority(self):
        self.assertEqual(self.provider.calls,0)
        app=self.f.application
        for token,site in [(self.f.b,self.f.site_a),(self.f.b,self.f.site_b)]:
            with self.assertRaises(PermissionError):app.advice(token,site,self.scan['scan_id'],generate=True,advisor=self.engine)
        result=app.advice(self.f.a,self.f.site_a,self.scan['scan_id'],generate=True,advisor=self.engine)
        self.assertEqual(result['status'],'model-assisted');self.assertEqual(self.provider.calls,1)
        self.assertEqual(app.history(self.f.a,self.f.site_a),[])
        self.assertTrue(all(x['autofix'] is False for x in result['recommendations']))
        self.f.auth.logout(self.f.a);new=self.f.auth.login('alice','Alice-unified-password')
        self.assertEqual(app.advice(new,self.f.site_a,self.scan['scan_id']),result)
        self.f.monitor.configure(new,self.f.site_a,enabled=True,page_limit=1,max_requests=3)
        with patch('contextual_advisor.configured_advisor',side_effect=AssertionError('Monitoring must not invoke inference')):
            self.f.monitor.run_once()
        self.assertEqual(self.provider.calls,1)
    def test_app_ui_shows_model_provenance_evidence_and_never_exposes_apply_button(self):
        with patch('guard_application_ui.configured_guard_application',return_value=self.f.application),patch('contextual_advisor.configured_advisor',return_value=self.engine):
            at=AppTest.from_file('app.py',default_timeout=30)
            at.session_state['fg_customer_session']=self.f.a;at.run()
            next(x for x in at.button if x.label=='Analyze context with AI').click();at.run()
            self.assertEqual(list(at.exception),[])
            self.assertTrue(any('model-assisted' in x.value for x in at.caption))
            self.assertTrue(any('Handmade oak' in x.value for x in at.text))
            self.assertTrue(any('reviewed templates' in x.value for x in at.caption))
            self.assertTrue(any('Verify the missing' in x.value for x in at.text))
            self.assertFalse(any(x.label=='Approve and apply test change' for x in at.button))
            next(x for x in at.button if x.label=='Prepare exact repair proposal').click();at.run()
            self.assertTrue(next(x for x in at.button if x.label=='Approve and apply test change').disabled)
    def test_missing_configuration_falls_back_without_claiming_model_inference(self):
        with patch('contextual_advisor.configured_advisor',return_value=None):
            result=self.f.application.advice(self.f.a,self.f.site_a,self.scan['scan_id'],generate=True)
        self.assertEqual(result['status'],'model-not-configured');self.assertTrue(all(x['source']=='rules' for x in result['recommendations']))

    def test_ledger_failure_preserves_readonly_scanner_advice_without_inference(self):
        from advisor_ledger import AdvisorLedgerError
        with patch('contextual_advisor.configured_advisor',side_effect=AdvisorLedgerError('private operational detail')):
            result=self.f.application.advice(self.f.a,self.f.site_a,self.scan['scan_id'],generate=True)
        self.assertEqual(result['status'],'usage-ledger-unavailable')
        self.assertTrue(all(x['source']=='rules' and x['autofix'] is False for x in result['recommendations']))
        self.assertNotIn('private operational detail',json.dumps(result))
        self.assertEqual(self.provider.calls,0)
        self.assertEqual(self.f.application.advice(self.f.a,self.f.site_a,self.scan['scan_id']),result)

    def test_live_ledger_failure_does_not_bypass_customer_scope(self):
        from advisor_ledger import AdvisorLedgerError
        engine=unittest.mock.Mock()
        engine.analyze.side_effect=AdvisorLedgerError('private detail')
        with self.assertRaises(PermissionError):
            self.f.application.advice(self.f.b,self.f.site_a,self.scan['scan_id'],generate=True,advisor=engine)
        engine.analyze.assert_not_called()
        result=self.f.application.advice(self.f.a,self.f.site_a,self.scan['scan_id'],generate=True,advisor=engine)
        self.assertEqual(result['status'],'usage-ledger-unavailable')
        self.assertNotIn('private detail',json.dumps(result))
