from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stdout
from io import StringIO
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch
import test_monitoring_service as fixture
from monitoring_email import DeliveryNotStarted,DeliveryUncertain
from monitoring_email_configuration import configured_email_dispatcher,DailyBudgetSender
from monitoring_worker import main
from monitoring_service import MonitoringService

class EmailOperationsTests(unittest.TestCase):
    def setUp(self):
        self.f=fixture.MonitoringServiceTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.f.enable();self.f.monitor.run_once(now=100)
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.credentials=self.root/'smtp.json';self.credentials.write_text(json.dumps({'username':'fixture','password':'synthetic-secret'}));self.credentials.chmod(0o600)
        self.bindings=self.root/'bindings.json'
        self.rows=[{'customer_id':self.f.alice.customer_id,'address':'verified@example.test','verified_at':1,'consent':True}]
        self.write_bindings()
        self.env={'FG_EMAIL_AUTHORIZED':'1','FG_SMTP_CREDENTIALS_FILE':str(self.credentials),
            'FG_EMAIL_BINDINGS_FILE':str(self.bindings),'FG_SMTP_SENDER':'alerts@example.test','FG_SMTP_DAILY_LIMIT':'2'}
    def write_bindings(self):self.bindings.write_text(json.dumps(self.rows));self.bindings.chmod(0o600)
    def test_unconfigured_sender_neither_reads_credentials_nor_connects(self):
        with patch.dict(os.environ,{},clear=True),patch('monitoring_email_configuration.private_file') as read:
            self.assertIsNone(configured_email_dispatcher(self.f.monitor));read.assert_not_called()
    def test_configured_brevo_tls_dispatch_without_real_email(self):
        connection=Mock();connection.send_message.return_value={}
        with patch.dict(os.environ,self.env,clear=True),patch('smtplib.SMTP',return_value=connection) as smtp:
            dispatcher=configured_email_dispatcher(self.f.monitor)
            self.assertEqual(dispatcher.dispatch_once(now=3600)['status'],'sent')
            self.assertEqual(dispatcher.dispatch_once(now=3601)['status'],'idle')
        smtp.assert_called_once_with('smtp-relay.brevo.com',587,timeout=10)
        self.assertTrue(connection.starttls.call_args.kwargs['context'].check_hostname)
        self.assertEqual(connection.send_message.call_args.kwargs['to_addrs'],['verified@example.test'])
    def test_unverified_revoked_or_wrong_account_never_receives(self):
        for change in [{'consent':False},{'verified_at':0},{'revoked':True},{'customer_id':self.f.bob.customer_id}]:
            self.rows=[{**self.rows[0],**change}];self.write_bindings()
            with patch.dict(os.environ,self.env,clear=True),patch('smtplib.SMTP') as smtp:
                dispatcher=configured_email_dispatcher(self.f.monitor)
                self.assertIsNone(dispatcher.recipients(self.f.alice.customer_id));smtp.assert_not_called()
    def test_binding_revocation_is_observed_after_configuration(self):
        with patch.dict(os.environ,self.env,clear=True),patch('smtplib.SMTP') as smtp:
            dispatcher=configured_email_dispatcher(self.f.monitor)
            self.rows[0]['revoked']=True;self.write_bindings()
            self.assertEqual(dispatcher.dispatch_once(now=3600)['status'],'blocked');smtp.assert_not_called()
    def test_daily_quota_is_atomic_persistent_and_never_refunds_unknown_sends(self):
        sender=Mock();sender.send.return_value={'accepted':True}
        budget=DailyBudgetSender(self.f.monitor,sender,limit=2,clock=lambda:100)
        def send():
            try:budget.send({},None);return True
            except DeliveryNotStarted:return False
        with ThreadPoolExecutor(max_workers=8) as pool:self.assertEqual(sum(pool.map(lambda _:send(),range(8))),2)
        reopened=MonitoringService(self.f.directory,self.f.path,scanner=self.f.scanner)
        with self.assertRaises(DeliveryNotStarted):DailyBudgetSender(reopened,sender,limit=2,clock=lambda:101).send({},None)
        sender.send.side_effect=DeliveryUncertain('lost acknowledgment')
        next_day=DailyBudgetSender(reopened,sender,limit=1,clock=lambda:86500)
        with self.assertRaises(DeliveryUncertain):next_day.send({},None)
        with self.assertRaises(DeliveryNotStarted):next_day.send({},None)
    def test_worker_calls_opt_in_dispatcher_without_needing_browser_session(self):
        dispatcher=Mock();dispatcher.dispatch_once.return_value={'status':'sent','sent':1}
        with redirect_stdout(StringIO()):
            self.assertEqual(main(['--once'],service=self.f.monitor,email_dispatcher=dispatcher),0)
        dispatcher.dispatch_once.assert_called_once()
