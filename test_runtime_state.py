import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
from operations_guard_setup import initialize_read_only
from monitoring_configuration import configured_monitoring
from runtime_state import require_existing_guard_state, require_existing_database, AUTH_TABLES


class PersistentRuntimeStateTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.env={'FG_CUSTOMER_AUTH_DB':str(self.root/'auth.sqlite'),
                  'FG_CUSTOMER_DATA_ROOT':str(self.root/'sites'),
                  'FG_MONITOR_DB':str(self.root/'monitor.sqlite')}
    def test_missing_account_storage_disables_ui_without_creating_database(self):
        env={**self.env,'FG_CUSTOMER_REGISTRATION':'1'}
        with patch.dict(os.environ,env,clear=True):
            app=AppTest.from_string('from customer_account_ui import render_customer_account\nrender_customer_account()').run()
        self.assertFalse(app.exception);self.assertEqual(len(app.text_input),0)
        self.assertTrue(app.warning);self.assertFalse(Path(self.env['FG_CUSTOMER_AUTH_DB']).exists())
    def test_corrupt_account_storage_keeps_scanner_page_usable_and_clears_session(self):
        path=Path(self.env['FG_CUSTOMER_AUTH_DB']);path.write_bytes(b'corrupt');path.chmod(0o600)
        code="import streamlit as st\nfrom customer_account_ui import render_customer_account\nrender_customer_account()\nst.write('Scanner available')"
        with patch.dict(os.environ,self.env,clear=True):
            app=AppTest.from_string(code)
            app.session_state['fg_customer_session']='old-session'
            app.session_state['fg_customer_plan']='old-plan';app.run()
        self.assertFalse(app.exception);self.assertTrue(any('Scanner available' in x.value for x in app.markdown))
        with self.assertRaises(KeyError):_=app.session_state['fg_customer_session']
        self.assertEqual(path.read_bytes(),b'corrupt')
    def test_missing_monitoring_state_does_not_recreate_history_or_outbox(self):
        initialize_read_only(self.env)
        path=Path(self.env['FG_MONITOR_DB']);path.rename(self.root/'saved-monitor.sqlite')
        with patch.dict(os.environ,self.env,clear=True),self.assertRaises(ValueError):configured_monitoring()
        self.assertFalse(path.exists())
    def test_bootstrap_refuses_each_partial_state_without_replacing_remaining_data(self):
        initialize_read_only(self.env)
        paths=[Path(x) for x in require_existing_guard_state(self.env)]
        for path in paths:
            saved=path.with_suffix('.saved');before={p:p.read_bytes() for p in paths if p!=path}
            path.rename(saved)
            with self.assertRaises(ValueError):initialize_read_only(self.env)
            self.assertFalse(path.exists())
            self.assertTrue(all(p.read_bytes()==data for p,data in before.items()))
            saved.rename(path)
    def test_valid_state_check_is_read_only_and_preserves_call_ledger(self):
        initialize_read_only(self.env);ledger=self.root/'ledger.sqlite';ledger.write_bytes(b'untouched-ai-history')
        paths=[Path(x) for x in require_existing_guard_state(self.env)]
        before={p:p.read_bytes() for p in paths}
        require_existing_guard_state(self.env)
        self.assertTrue(all(p.read_bytes()==data for p,data in before.items()))
        self.assertEqual(ledger.read_bytes(),b'untouched-ai-history')
    def test_restore_hold_symlink_and_public_permissions_rejected(self):
        initialize_read_only(self.env);path=Path(self.env['FG_CUSTOMER_AUTH_DB'])
        link=self.root/'link.sqlite';link.symlink_to(path)
        with self.assertRaises(ValueError):require_existing_database(link,AUTH_TABLES)
        path.chmod(0o644)
        with self.assertRaises(ValueError):require_existing_guard_state(self.env)
        path.chmod(0o600);(self.root/'FG-RESTORE-REVIEW-REQUIRED').write_text('pending')
        with self.assertRaises(ValueError):require_existing_guard_state(self.env)
    def test_same_database_cannot_be_reused_for_different_state_roles(self):
        initialize_read_only(self.env);self.env['FG_MONITOR_DB']=self.env['FG_CUSTOMER_AUTH_DB']
        with self.assertRaises(ValueError):require_existing_guard_state(self.env)


if __name__=='__main__':unittest.main()
