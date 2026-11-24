"""Full Streamlit entry point with isolated simulated WordPress/storage."""
import unittest
from unittest.mock import patch
import test_guard_application as fixture
from streamlit.testing.v1 import AppTest

class IntegratedUITests(unittest.TestCase):
    def setUp(self):
        self.f=fixture.UnifiedFlowTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.f.application.allow_registration=True
        self.patcher=patch('guard_application_ui.configured_guard_application',return_value=self.f.application)
        self.patcher.start();self.addCleanup(self.patcher.stop)
        self.at=AppTest.from_file('app.py',default_timeout=30).run()
    def run_ui(self):
        self.at.run();self.assertEqual(list(self.at.exception),[])
        self.assertFalse(any('could not be verified' in e.value for e in self.at.error))
    def text(self,label,value):
        next(x for x in self.at.text_input if x.label==label).set_value(value)
    def click(self,label):
        next(x for x in self.at.button if x.label==label).click();self.run_ui()
    def check(self,label,value=True):
        next(x for x in self.at.checkbox if x.label==label).set_value(value);self.run_ui()
    def test_main_entry_login_scan_approve_backup_repair_restore_monitor_restart(self):
        self.text('Account username','alice');self.text('Account password','Alice-unified-password');self.click('Sign in')
        source=self.f.origins[0]+'/source/'
        next(x for x in self.at.selectbox if x.label=='Page to scan').set_value(source)
        self.click('Scan authorized site');self.click('Prepare exact repair proposal')
        self.assertTrue(next(x for x in self.at.button if x.label=='Approve and apply test change').disabled)
        self.check('I approve exactly this change');self.click('Approve and apply test change')
        self.assertTrue(any('applied and verified' in x.value for x in self.at.success))
        self.click('Recheck changed page')
        token=self.at.session_state['fg_customer_session']
        self.assertEqual(self.f.application.scan_record(token,self.f.site_a)['report']['broken'],[])
        self.click('Review rollback');self.check('I approve exactly this change');self.click('Approve and apply test change')
        next(x for x in self.at.checkbox if x.label=='Enable periodic monitoring').set_value(True);self.click('Save monitoring settings')
        self.assertEqual(self.f.monitor.run_once()['status'],'complete');self.run_ui()
        self.assertTrue(self.f.monitor.history(token,self.f.site_a))
        self.assertTrue(self.f.monitor.notifications(token))
        self.click('Sign out')
        self.text('Account username','alice');self.text('Account password','Alice-unified-password');self.click('Sign in')
        self.assertTrue(any('Repair and recovery history' in x.value for x in self.at.markdown))
        self.assertEqual(len(self.f.application.history(self.at.session_state['fg_customer_session'],self.f.site_a)),2)
        self.assertNotIn('https://bob.test',str([x.value for x in self.at.markdown]))

    def test_registration_and_site_authorization_use_ui_only(self):
        self.check('Create an account');self.text('Account username','carol');self.text('Account password','Carol-unified-password')
        self.click('Create account')
        # The first two sites already have distinct owners. A third account cannot steal either.
        self.text('WordPress username','admin');self.text('WordPress Application Password','synthetic-application-password')
        self.click('Authorize site')
        self.assertTrue(any('authorization failed' in x.value for x in self.at.error))
        self.assertEqual(self.f.sites.list_sites(self.at.session_state['fg_customer_session']),[])
