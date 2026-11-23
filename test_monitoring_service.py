from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from customer_auth import CustomerAuth,AuthenticationError
from customer_sites import CustomerSites
from monitoring_service import MonitoringService,LeaseLost
from monitoring_scan import make_report


def report(origin,missing=True,error=False):
    row=dict(page=origin,http_status='ERROR' if error else 200,title='Home',
        meta_description='' if missing else 'A useful description',h1_count=1,images_missing_alt=0,issues='')
    return make_report([row],[],[],1,not error)


class FixtureScanner:
    def __init__(self):self.missing=True;self.error=False;self.calls=[];self.callback=None
    def __call__(self,origin,*,before_request,checkpoint,**kwargs):
        self.calls.append(origin);checkpoint();before_request()
        if self.callback:self.callback()
        checkpoint()
        return report(origin,self.missing,self.error)


class MonitoringServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);root=Path(self.temp.name)
        self.auth=CustomerAuth(root/'auth.sqlite')
        self.alice=self.auth.register('alice','Alice-monitor-password')
        self.bob=self.auth.register('bob','Bob-monitor-password')
        self.a=self.auth.login('alice','Alice-monitor-password',now=100)
        self.b=self.auth.login('bob','Bob-monitor-password',now=100)
        self.directory=CustomerSites(self.auth,root/'sites',None)
        self.site_a='a'*32;self.site_b='b'*32
        self.origin_a='https://alice.example';self.origin_b='https://bob.example'
        with self.directory.db() as db:
            for site,customer,origin in [(self.site_a,self.alice.customer_id,self.origin_a),(self.site_b,self.bob.customer_id,self.origin_b)]:
                db.execute('INSERT INTO customer_sites VALUES (?, ?, ?, 7, ?, ?, 100)',(site,customer,origin,'unavailable-key',b'not-decrypted'))
        self.scanner=FixtureScanner();self.path=root/'monitor.sqlite'
        self.monitor=MonitoringService(self.directory,self.path,scanner=self.scanner)

    def enable(self,token=None,site=None,**kwargs):
        return self.monitor.configure(token or self.a,site or self.site_a,enabled=True,
            interval_seconds=900,page_limit=1,max_requests=3,now=100,**kwargs)

    def refresh_session(self,token,now):
        # Tests advance scheduling hours; customer browser sessions remain independent.
        with self.auth.db() as db:
            db.execute('UPDATE customer_sessions SET last_seen=?,expires_at=? WHERE token_digest=?',
                       (now,now+3600,self.auth.token_digest(token)))

    def test_schedule_runs_only_when_due_and_persists_history(self):
        self.enable();self.assertEqual(self.monitor.run_once(now=99)['status'],'idle')
        first=self.monitor.run_once(now=100);self.assertEqual(first['status'],'complete')
        self.assertFalse(first['repairs_authorized']);self.assertEqual(first['new'],1)
        self.assertEqual(self.monitor.run_once(now=101)['status'],'idle')
        self.monitor.run_once(now=1000);self.refresh_session(self.a,1001)
        self.assertEqual(len(self.monitor.history(self.a,self.site_a,now=1001)),2)
        self.assertEqual(len(self.scanner.calls),2)

    def test_two_customers_have_separate_settings_history_findings_and_alerts(self):
        self.enable();self.enable(self.b,self.site_b)
        self.monitor.run_once(now=100);self.monitor.run_once(now=100)
        self.assertEqual(self.monitor.snapshot(self.a,self.site_a,now=101)['findings'][0]['page'],self.origin_a)
        self.assertEqual(self.monitor.snapshot(self.b,self.site_b,now=101)['findings'][0]['page'],self.origin_b)
        for operation in (lambda:self.monitor.snapshot(self.b,self.site_a,now=101),
                          lambda:self.monitor.history(self.b,self.site_a,now=101),
                          lambda:self.monitor.configure(self.b,self.site_a,enabled=False,now=101)):
            with self.assertRaises(PermissionError):operation()
        notification=self.monitor.notifications(self.a,now=101)[0]
        with self.assertRaises(PermissionError):self.monitor.mark_read(self.b,notification['notification_id'],now=101)
        self.assertTrue(all(n['site_id']==self.site_b for n in self.monitor.notifications(self.b,now=101)))

    def test_expired_session_cannot_configure_but_authorized_background_consent_persists(self):
        self.enable()
        with self.assertRaises(AuthenticationError):self.monitor.configure(self.a,self.site_a,enabled=False,now=4000)
        self.assertEqual(self.monitor.run_once(now=4000)['status'],'complete')
        self.assertEqual(self.monitor.run_once(now=4001)['status'],'idle')

    def test_concurrent_workers_only_one_claims_the_due_slot(self):
        self.enable()
        with ThreadPoolExecutor(max_workers=8) as pool:jobs=list(pool.map(lambda _:self.monitor.claim(now=100),range(8)))
        self.assertEqual(sum(job is not None for job in jobs),1)

    def test_crash_recovery_reuses_run_and_rejects_old_worker_result(self):
        self.enable();old=self.monitor.claim(now=100)
        restarted=MonitoringService(self.directory,self.path,scanner=self.scanner)
        new=restarted.claim(now=190);self.assertEqual(old['run_id'],new['run_id'])
        self.assertNotEqual(old['lease_token'],new['lease_token'])
        with self.assertRaises(LeaseLost):self.monitor.publish(old,report(self.origin_a),now=191)
        restarted.publish(new,report(self.origin_a),now=191)
        self.assertEqual(len(self.monitor.history(self.a,self.site_a,now=192)),1)

    def test_repeated_publication_cannot_duplicate_results_or_notifications(self):
        self.enable();job=self.monitor.claim(now=100)
        self.monitor.publish(job,report(self.origin_a),now=101)
        with self.assertRaises(LeaseLost):self.monitor.publish(job,report(self.origin_a),now=102)
        self.assertEqual(len(self.monitor.history(self.a,self.site_a,now=103)),1)
        self.assertEqual(self.monitor.notifications(self.a,now=103)[0]['event_count'],1)

    def test_recovery_attempts_and_request_budget_are_persistent(self):
        self.enable();job=self.monitor.claim(now=100);self.monitor.reserve_request(job,now=100)
        job=self.monitor.claim(now=190);self.monitor.reserve_request(job,now=190)
        job=self.monitor.claim(now=280);self.monitor.reserve_request(job,now=280)
        with self.assertRaises(ValueError):self.monitor.reserve_request(job,now=281)
        self.assertIsNone(self.monitor.claim(now=370))
        self.assertEqual(self.monitor.history(self.a,self.site_a,now=371)[0]['state'],'error')
        self.assertEqual(self.monitor.notifications(self.a,now=371)[0]['kind'],'monitoring_error')

    def test_new_resolved_and_changed_issues_are_coalesced_without_unchanged_spam(self):
        self.enable();self.monitor.run_once(now=100);self.monitor.run_once(now=1000)
        self.scanner.missing=False;result=self.monitor.run_once(now=1900)
        self.assertEqual(result['resolved'],1);self.assertGreater(result['changed'],0)
        self.refresh_session(self.a,1901)
        notes=self.monitor.notifications(self.a,now=1901)
        self.assertEqual(len(notes),1);self.assertEqual(notes[0]['event_count'],2)
        self.assertEqual(self.monitor.snapshot(self.a,self.site_a,now=1901)['findings'],[])

    def test_network_failure_does_not_falsely_resolve_and_repeated_errors_do_not_spam(self):
        self.enable();self.monitor.run_once(now=100);self.scanner.error=True
        self.monitor.run_once(now=1000);self.monitor.run_once(now=1900)
        self.refresh_session(self.a,1901)
        self.assertEqual(len(self.monitor.snapshot(self.a,self.site_a,now=1901)['findings']),1)
        notes=self.monitor.notifications(self.a,now=1901)
        self.assertEqual(len([n for n in notes if n['kind']=='monitoring_error']),1)
        self.scanner.error=False;self.monitor.run_once(now=2800)
        self.refresh_session(self.a,2801)
        self.assertEqual(len([n for n in self.monitor.notifications(self.a,now=2801) if n['kind']=='monitoring_recovered']),1)

    def test_unscanned_pages_are_not_assumed_fixed(self):
        self.enable();job=self.monitor.claim(now=100)
        old=make_report([dict(page=self.origin_a+'/old',http_status=200,title='',meta_description='Good',h1_count=1,images_missing_alt=0)],[],[],1)
        self.monitor.publish(job,old,now=101)
        job=self.monitor.claim(now=1001);self.monitor.publish(job,report(self.origin_a,False),now=1002)
        self.refresh_session(self.a,1003)
        self.assertEqual(len(self.monitor.snapshot(self.a,self.site_a,now=1003)['findings']),1)

    def test_removed_broken_link_is_resolved_only_when_its_sources_were_checked(self):
        self.enable();job=self.monitor.claim(now=100);url=self.origin_a+'/missing'
        rows=[dict(page=self.origin_a,http_status=200,title='Good',meta_description='Good',h1_count=1,images_missing_alt=0)]
        old=make_report(rows,[dict(link=url,status=404,found_on=self.origin_a)],[url],1,link_sources={url:{self.origin_a}})
        self.monitor.publish(job,old,now=101)
        job=self.monitor.claim(now=1001);new=make_report(rows,[],[],1,link_sources={})
        self.assertEqual(self.monitor.publish(job,new,now=1002)['resolved'],1)

    def test_disabling_or_reconfiguring_fences_inflight_worker_and_prevents_hammering(self):
        self.enable();job=self.monitor.claim(now=100)
        self.monitor.configure(self.a,self.site_a,enabled=False,now=101)
        with self.assertRaises(LeaseLost):self.monitor.checkpoint(job,now=102)
        self.monitor.configure(self.a,self.site_a,enabled=True,interval_seconds=900,page_limit=1,max_requests=3,now=103)
        self.assertIsNone(self.monitor.claim(now=104))
        self.assertIsNotNone(self.monitor.claim(now=1000))

    def test_disable_during_scan_cannot_publish_stale_notifications(self):
        self.enable()
        self.scanner.callback=lambda:self.monitor.configure(self.a,self.site_a,enabled=False,now=101)
        self.assertIn(self.monitor.run_once(now=100)['status'],('cancelled','superseded'))
        self.assertEqual(self.monitor.notifications(self.a,now=102),[])
        self.assertEqual(self.monitor.history(self.a,self.site_a,now=102)[0]['state'],'cancelled')

    def test_monitoring_never_decrypts_credentials_or_calls_autofix(self):
        self.enable()
        with patch.object(self.directory,'_credentials',side_effect=AssertionError('No secrets')), \
             patch.object(self.directory,'apply',side_effect=AssertionError('No repair')):
            result=self.monitor.run_once(now=100)
        self.assertEqual(result['status'],'complete');self.assertFalse(result['repairs_authorized'])

    def test_revoked_account_stops_background_scan(self):
        self.enable()
        with self.auth.db() as db:db.execute('UPDATE customers SET active=0 WHERE customer_id=?',(self.alice.customer_id,))
        self.assertEqual(self.monitor.run_once(now=100)['status'],'idle');self.assertEqual(self.scanner.calls,[])

    def test_unsafe_settings_and_unbounded_history_rejected(self):
        for settings in (dict(interval_seconds=1),dict(page_limit=31),dict(max_requests=0),dict(enabled='yes')):
            kwargs=dict(enabled=True,interval_seconds=900,page_limit=1,max_requests=3);kwargs.update(settings)
            with self.assertRaises(ValueError):self.monitor.configure(self.a,self.site_a,now=100,**kwargs)
        with self.assertRaises(ValueError):self.monitor.history(self.a,self.site_a,limit=10000,now=100)

    def test_request_spacing_is_shared_between_attempts(self):
        self.enable();job=self.monitor.claim(now=100)
        self.assertEqual(self.monitor.reserve_request(job,now=100),0)
        self.assertEqual(self.monitor.reserve_request(job,now=100.25),.75)
        self.assertEqual(self.monitor.reserve_request(job,now=101),0)

    def test_catchup_after_long_downtime_schedules_future_without_burst(self):
        self.enable();self.monitor.run_once(now=100000)
        self.assertIsNone(self.monitor.claim(now=100001))
        with self.monitor.db() as db:due=db.execute('SELECT next_due FROM monitor_schedules').fetchone()[0]
        self.assertEqual(due,100900)
