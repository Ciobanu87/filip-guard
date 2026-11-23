from unittest.mock import Mock,patch
import unittest
from monitoring_email import (SMTPConfig,SMTPNotificationSender,VerifiedEmailBinding,
    EmailNotConfigured,DeliveryUncertain,DeliveryNotStarted,MonitoringEmailDispatcher)
import test_monitoring_service as fixtures


class SMTPAdapterTests(unittest.TestCase):
    def notice(self):
        return dict(notification_id='a'*32,customer_id='b'*32,payload=dict(origin='https://example.com',
            events=[dict(new_count=1,resolved_count=0,changed_count=0)]))
    def sender(self,**kwargs):
        return SMTPNotificationSender(SMTPConfig('smtp.example.test','alerts@example.test'),
            lambda:('fictitious-user','fictitious-secret'),**kwargs)

    def test_default_cannot_send_and_does_not_read_credentials(self):
        credentials=Mock();sender=SMTPNotificationSender(SMTPConfig('smtp.example.test','alerts@example.test'),credentials)
        with patch('smtplib.SMTP_SSL') as connect:
            with self.assertRaises(EmailNotConfigured):sender.send(self.notice(),VerifiedEmailBinding('b'*32,'user@example.test'))
            connect.assert_not_called();credentials.assert_not_called()

    def test_verified_tls_and_exact_customer_recipient_with_plaintext_digest(self):
        connection=Mock();connection.send_message.return_value={}
        with patch('smtplib.SMTP_SSL',return_value=connection) as connect:
            self.sender(authorized=True).send(self.notice(),VerifiedEmailBinding('b'*32,'user@example.test'))
        self.assertTrue(connect.call_args.kwargs['context'].check_hostname)
        connection.login.assert_called_once_with('fictitious-user','fictitious-secret')
        message=connection.send_message.call_args.args[0]
        self.assertEqual(message['To'],'user@example.test')
        self.assertNotIn('fictitious-secret',str(message));connection.close.assert_called_once()

    def test_wrong_account_or_header_injection_never_connects(self):
        with patch('smtplib.SMTP_SSL') as connect:
            with self.assertRaises(DeliveryNotStarted):self.sender(authorized=True).send(self.notice(),VerifiedEmailBinding('c'*32,'other@example.test'))
            with self.assertRaises(ValueError):self.sender(authorized=True).send(self.notice(),VerifiedEmailBinding('b'*32,'user@example.test\r\nBcc: other@example.test'))
            connect.assert_not_called()

    def test_lost_smtp_acknowledgment_is_unknown_and_secret_is_redacted(self):
        connection=Mock();connection.send_message.side_effect=TimeoutError('fictitious-secret')
        with patch('smtplib.SMTP_SSL',return_value=connection):
            with self.assertRaises(DeliveryUncertain) as caught:
                self.sender(authorized=True).send(self.notice(),VerifiedEmailBinding('b'*32,'user@example.test'))
        self.assertNotIn('fictitious-secret',str(caught.exception));connection.close.assert_called_once()

    def test_connection_failure_is_known_not_started(self):
        with patch('smtplib.SMTP_SSL',side_effect=OSError('fictitious-secret')):
            with self.assertRaises(DeliveryNotStarted):self.sender(authorized=True).send(self.notice(),VerifiedEmailBinding('b'*32,'user@example.test'))

    def test_starttls_precedes_login_and_uses_hostname_verification(self):
        connection=Mock();connection.send_message.return_value={}
        sender=SMTPNotificationSender(SMTPConfig('smtp.example.test','alerts@example.test',587,'starttls'),
            lambda:('fictitious-user','fictitious-secret'),authorized=True)
        with patch('smtplib.SMTP',return_value=connection):
            sender.send(self.notice(),VerifiedEmailBinding('b'*32,'user@example.test'))
        methods=[call[0] for call in connection.method_calls]
        self.assertLess(methods.index('starttls'),methods.index('login'))
        self.assertTrue(connection.starttls.call_args.kwargs['context'].check_hostname)

    def test_no_plaintext_smtp_configuration(self):
        for config in (SMTPConfig('smtp.example.test','alerts@example.test',25,'plain'),
                       SMTPConfig('smtp.example.test','alerts@example.test',587,'ssl')):
            with self.assertRaises(ValueError):config.validate()


class EmailQueueTests(unittest.TestCase):
    def setUp(self):
        self.fixture=fixtures.MonitoringServiceTests();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.fixture.enable();self.fixture.monitor.run_once(now=100)
        self.sender=Mock();self.sender.send.return_value={'accepted':True};self.dispatcher=MonitoringEmailDispatcher(self.fixture.monitor,sender=self.sender,
            recipient_resolver=lambda cid:VerifiedEmailBinding(cid,'verified@example.test'))

    def test_disabled_sender_cannot_send(self):
        self.assertEqual(MonitoringEmailDispatcher(self.fixture.monitor).dispatch_once(now=3600)['status'],'disabled')
        self.sender.send.assert_not_called()

    def test_window_delay_and_duplicate_delivery_prevention(self):
        self.assertEqual(self.dispatcher.dispatch_once(now=101)['status'],'idle')
        self.assertEqual(self.dispatcher.dispatch_once(now=3600)['status'],'sent')
        self.assertEqual(self.dispatcher.dispatch_once(now=3601)['status'],'idle')
        self.sender.send.assert_called_once()

    def test_wrong_account_recipient_is_blocked(self):
        self.dispatcher.recipients=lambda cid:VerifiedEmailBinding(self.fixture.bob.customer_id,'bob@example.test')
        self.assertEqual(self.dispatcher.dispatch_once(now=3600)['status'],'blocked')
        self.sender.send.assert_not_called()

    def test_uncertain_delivery_is_not_automatically_repeated(self):
        self.sender.send.side_effect=DeliveryUncertain('Lost acknowledgment')
        self.assertEqual(self.dispatcher.dispatch_once(now=3600)['status'],'unknown')
        self.assertEqual(self.dispatcher.dispatch_once(now=7200)['status'],'idle')
        self.sender.send.assert_called_once()

    def test_crashed_delivery_is_quarantined_without_resend(self):
        with self.fixture.monitor.db() as db:
            db.execute("UPDATE monitor_email_outbox SET state='sending',lease_until=3500,attempted_at=3400")
        self.assertEqual(self.dispatcher.dispatch_once(now=3600)['status'],'idle')
        with self.fixture.monitor.db() as db:state=db.execute('SELECT state FROM monitor_email_outbox').fetchone()[0]
        self.assertEqual(state,'unknown');self.sender.send.assert_not_called()

    def test_pre_send_failure_is_retryable_but_bounded(self):
        self.sender.send.side_effect=DeliveryNotStarted('Transport unavailable')
        for now,status in [(3600,'pending'),(7200,'pending'),(10800,'failed')]:
            self.assertEqual(self.dispatcher.dispatch_once(now=now)['status'],status)
        self.assertEqual(self.dispatcher.dispatch_once(now=14400)['status'],'idle')
        self.assertEqual(self.sender.send.call_count,3)

    def test_account_rate_limit_applies_across_multiple_site_alert_types(self):
        self.fixture.scanner.error=True;self.fixture.monitor.run_once(now=1000)
        self.assertEqual(self.dispatcher.dispatch_once(now=3600)['status'],'sent')
        self.assertEqual(self.dispatcher.dispatch_once(now=3600)['status'],'idle')
        self.assertEqual(self.dispatcher.dispatch_once(now=7200)['status'],'sent')
        self.assertEqual(self.sender.send.call_count,2)

    def test_unverified_sender_receipt_is_not_reported_as_sent(self):
        self.sender.send.return_value=None
        self.assertEqual(self.dispatcher.dispatch_once(now=3600)['status'],'unknown')
        self.assertEqual(self.dispatcher.dispatch_once(now=7200)['status'],'idle')
        self.sender.send.assert_called_once()

    def test_old_pending_alerts_expire_without_a_startup_mail_burst(self):
        self.assertEqual(self.dispatcher.dispatch_once(now=90000)['status'],'idle')
        self.sender.send.assert_not_called()
        with self.fixture.monitor.db() as db:state=db.execute('SELECT state FROM monitor_email_outbox').fetchone()[0]
        self.assertEqual(state,'expired')

    def test_concurrent_dispatcher_startup_migrates_schema_once(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        with self.fixture.monitor.db() as db:
            db.execute('ALTER TABLE monitor_email_outbox DROP COLUMN attempted_at')
        barrier=Barrier(8)
        def start(_):
            barrier.wait()
            return MonitoringEmailDispatcher(self.fixture.monitor)
        with ThreadPoolExecutor(max_workers=8) as pool:
            self.assertEqual(len(list(pool.map(start,range(8)))),8)
        with self.fixture.monitor.db() as db:
            columns=[row[1] for row in db.execute('PRAGMA table_info(monitor_email_outbox)')]
        self.assertEqual(columns.count('attempted_at'),1)

    def test_concurrent_dispatchers_cannot_send_same_notification_twice(self):
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=8) as pool:
            results=list(pool.map(lambda _:self.dispatcher.dispatch_once(now=3600),range(8)))
        self.assertEqual(sum(result['sent'] for result in results),1)
        self.sender.send.assert_called_once()
