from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock,patch
import time

from streamlit.testing.v1 import AppTest
from customer_auth import CustomerAuth
from customer_sites import CustomerSites
from monitoring_service import MonitoringService
from monitoring_configuration import configured_monitoring
from monitoring_worker import main
import test_monitoring_service as fixtures


class MonitoringUITests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.auth=CustomerAuth(self.root/'auth.sqlite')
        alice=self.auth.register('alice','Alice-monitor-UI-password');bob=self.auth.register('bob','Bob-monitor-UI-password')
        self.a=self.auth.login('alice','Alice-monitor-UI-password');self.b=self.auth.login('bob','Bob-monitor-UI-password')
        self.directory=CustomerSites(self.auth,self.root/'sites',None)
        self.site_a='a'*32;self.site_b='b'*32
        with self.directory.db() as db:
            for site,owner,origin in [(self.site_a,alice.customer_id,'https://alice.example'),(self.site_b,bob.customer_id,'https://bob.example')]:
                db.execute('INSERT INTO customer_sites VALUES (?, ?, ?, 7, ?, ?, ?)',(site,owner,origin,'unavailable',b'not-decrypted',time.time()))
        self.monitor=MonitoringService(self.directory,self.root/'monitor.sqlite',scanner=fixtures.FixtureScanner())

    def app(self,token=None):
        app=AppTest.from_string("import streamlit as st\nfrom monitoring_ui import render_monitoring\nrender_monitoring(service=st.session_state['fixture_service'])")
        app.session_state['fixture_service']=self.monitor
        if token:app.session_state['fg_customer_session']=token
        return app.run()

    def test_anonymous_ui_has_no_controls(self):
        app=self.app();self.assertFalse(app.exception)
        self.assertEqual(len(app.selectbox),0);self.assertEqual(len(app.button),0)

    def test_configure_history_notifications_and_read_ack_without_network(self):
        with patch('socket.create_connection') as network:
            app=self.app(self.a)
            app.checkbox[0].check();app.number_input[0].set_value(1)
            app.button[0].click().run()
            self.assertFalse(app.exception)
            self.assertTrue(self.monitor.snapshot(self.a,self.site_a)['schedule']['enabled'])
            self.monitor.run_once();app.run()
            self.assertFalse(app.exception)
            self.assertTrue(len(app.dataframe)>=2)
            self.assertFalse(any('repair' in button.label.lower() for button in app.button))
            acknowledge=next(button for button in app.button if button.label=='Mark as read')
            acknowledge.click().run()
            self.assertIsNotNone(self.monitor.notifications(self.a)[0]['read_at'])
            app.checkbox[0].uncheck();app.button[0].click().run()
            self.assertFalse(self.monitor.snapshot(self.a,self.site_a)['schedule']['enabled'])
            network.assert_not_called()

    def test_each_account_only_sees_its_own_site(self):
        for token,origin in [(self.a,'https://alice.example'),(self.b,'https://bob.example')]:
            app=self.app(token);self.assertFalse(app.exception)
            self.assertEqual(app.selectbox[0].options,[origin])

    def test_expired_session_cannot_control_monitoring(self):
        self.auth.logout(self.a);app=self.app(self.a)
        self.assertFalse(app.exception);self.assertEqual(len(app.selectbox),0)
        self.assertTrue(any('expired' in warning.value for warning in app.warning))

    def test_trusted_configuration_loads_metadata_without_master_keys(self):
        with patch.dict('os.environ',dict(FG_CUSTOMER_AUTH_DB=str(self.root/'auth.sqlite'),
            FG_CUSTOMER_DATA_ROOT=str(self.root/'sites'),FG_MONITOR_DB=str(self.root/'monitor.sqlite'))):
            service=configured_monitoring()
        self.assertIsNone(service.directory.master_keys);self.assertIsNone(service.directory.gateway_factory)
        self.assertFalse(service.health()['worker_recent'])


class MonitoringWorkerTests(unittest.TestCase):
    def test_bounded_once_batch_and_no_email(self):
        service=Mock();service.run_once.side_effect=[{'status':'complete'},{'status':'idle'}]
        out=StringIO()
        with redirect_stdout(out),patch('smtplib.SMTP_SSL') as email:
            self.assertEqual(main(['--once','--max-jobs','2'],service=service),0)
            email.assert_not_called()
        summary=json.loads(out.getvalue());self.assertEqual(summary['processed'],1)
        self.assertFalse(summary['repairs_authorized'])

    def test_missing_configuration_stays_disabled(self):
        with patch('monitoring_worker.configured_monitoring',return_value=None),redirect_stdout(StringIO()):
            self.assertEqual(main(['--once']),2)

    def test_daemon_stops_cleanly_without_starting_more_work(self):
        stop=threading.Event();service=Mock()
        def scan():stop.set();return {'status':'complete'}
        service.run_once.side_effect=scan
        with redirect_stdout(StringIO()):self.assertEqual(main([],service=service,stop_event=stop),0)
        service.run_once.assert_called_once()
