import unittest
from pathlib import Path
from unittest.mock import Mock, patch
import test_monitoring_service as fixture
import test_contextual_advisor as ai
from contextual_advisor import ContextualAdvisor
from public_scan_advisor import analyze_owned_scan, owned_scan


class PublicScanAdvisorTests(unittest.TestCase):
    def setUp(self):
        self.f = fixture.MonitoringServiceTests(); self.f.setUp(); self.addCleanup(self.f.doCleanups)
        # Existing synthetic fixture sessions use time 100; renew to current time.
        self.a = self.f.auth.login('alice', 'Alice-monitor-password')
        self.b = self.f.auth.login('bob', 'Bob-monitor-password')
        page = self.f.origin_a + '/tables'
        self.scan = {'start_url':page, 'rows':[{**ai.ROWS[0], 'page':page}], 'contexts':{page:ai.CONTEXT[ai.ROWS[0]['page']]}}
        self.provider = ai.SimulatedProvider()
        self.engine = ContextualAdvisor(Path(self.f.auth.path).parent/'advisor.sqlite', self.provider)

    def test_authenticated_owner_gets_model_advice_and_same_scan_reuses_budget(self):
        one = analyze_owned_scan(self.f.directory, self.a, self.scan, engine=self.engine)
        two = analyze_owned_scan(self.f.directory, self.a, self.scan, engine=self.engine, language='ro')
        self.assertEqual(one['status'], 'model-assisted'); self.assertEqual(two['status'], 'model-assisted')
        self.assertEqual(self.provider.calls, 1)
        self.assertTrue(all(not item['autofix'] and not item['repair_supported'] for item in one['recommendations']))

    def test_anonymous_expired_or_other_owner_cannot_invoke_provider(self):
        for token in (None, self.b):
            with self.assertRaises(PermissionError): analyze_owned_scan(self.f.directory, token, self.scan, engine=self.engine)
        self.f.auth.logout(self.a)
        with self.assertRaises(PermissionError): analyze_owned_scan(self.f.directory, self.a, self.scan, engine=self.engine)
        self.assertEqual(self.provider.calls, 0)

    def test_cross_origin_pages_or_context_are_rejected(self):
        for scan in ({**self.scan, 'contexts':{'https://other.test/':'untrusted'}},
                     {**self.scan, 'rows':[{**self.scan['rows'][0], 'page':'https://other.test/'}]}):
            with self.assertRaises(PermissionError): analyze_owned_scan(self.f.directory, self.a, scan, engine=self.engine)
        self.assertEqual(self.provider.calls, 0)

    def test_missing_shared_ledger_is_not_replaced(self):
        path = Path(self.f.auth.path).parent/'missing.sqlite'
        with patch.dict('os.environ', {'FG_AI_LEDGER_DB':str(path)}), patch('public_scan_advisor.configured_advisor') as configured:
            with self.assertRaises(ValueError): analyze_owned_scan(self.f.directory, self.a, self.scan)
            configured.assert_not_called()
        self.assertFalse(path.exists())

    def test_revoked_ownership_rechecked_even_for_existing_scan(self):
        owned_scan(self.f.directory, self.a, self.scan)
        with self.f.directory.db() as db: db.execute('DELETE FROM customer_sites WHERE site_id=?', (self.f.site_a,))
        with self.assertRaises(PermissionError): analyze_owned_scan(self.f.directory, self.a, self.scan, engine=self.engine)
        self.assertEqual(self.provider.calls, 0)

    def test_streamlit_owner_button_and_language_switch_reuse_existing_ledger(self):
        from streamlit.testing.v1 import AppTest
        import json
        root = Path(self.f.auth.path).parent
        code = ('import streamlit as st\nfrom types import SimpleNamespace\n'
            'from customer_auth import CustomerAuth\nfrom customer_sites import CustomerSites\n'
            'from contextual_advisor import ContextualAdvisor\nfrom test_contextual_advisor import SimulatedProvider\n'
            'from public_scan_advisor import render_public_scan_advice\n'
            'st.session_state["fg_customer_session"] = '+repr(self.a)+'\n'
            'service=SimpleNamespace(directory=CustomerSites(CustomerAuth('+repr(str(root/'auth.sqlite'))+'),'+repr(str(root/'sites'))+',None))\n'
            'engine=ContextualAdvisor('+repr(str(root/'ui-ledger.sqlite'))+',SimulatedProvider())\n'
            'render_public_scan_advice(st,'+repr(self.scan)+',service=service,engine=engine)')
        app = AppTest.from_string(code).run()
        self.assertFalse(app.exception)
        self.assertTrue(any('Analysis status: rules' in item.value for item in app.caption))
        app.button[0].click().run()
        self.assertFalse(app.exception)
        self.assertTrue(any('Analysis status: model-assisted' in item.value for item in app.caption))
        app.selectbox[0].select('ro').run()
        self.assertFalse(app.exception)
        import sqlite3
        with sqlite3.connect(root/'ui-ledger.sqlite') as db:
            self.assertEqual(db.execute('SELECT SUM(calls) FROM advisor_budget').fetchone()[0], 1)
        self.assertFalse(any('apply' in button.label.lower() or 'repair' in button.label.lower() for button in app.button))
