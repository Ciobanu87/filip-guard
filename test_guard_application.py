from pathlib import Path
import secrets
import tempfile
import unittest
from unittest.mock import patch
from bs4 import BeautifulSoup

from customer_auth import CustomerAuth,AuthenticationError
from customer_sites import CustomerSites
from guard_application import GuardApplication,UnsupportedRepair,replace_broken_href
from monitoring_service import MonitoringService
from monitoring_scan import make_report,target_url
from website_scanner import scan
from wordpress_local_fixture import LocalWordPressFixture
from wordpress_revision_guard import RevisionMismatchError
from wordpress_encrypted_backup import EncryptedBackupError
from test_verified_external_backups import MemoryStore


class UnifiedFlowTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.auth=CustomerAuth(self.root/'auth.sqlite')
        self.auth.register('alice','Alice-unified-password');self.auth.register('bob','Bob-unified-password')
        self.a=self.auth.login('alice','Alice-unified-password');self.b=self.auth.login('bob','Bob-unified-password')
        self.master=secrets.token_bytes(32);self.store=MemoryStore()
        self.origins=['https://alice.test','https://bob.test'];self.backends={}
        for index,origin in enumerate(self.origins):
            backend=LocalWordPressFixture(self.root/f'wordpress-{index}.sqlite')
            backend.seed(origin,'post',1,f'<h1>Source</h1><p><a class="keep" href="{origin}/missing-destination/">Broken</a></p>',user_id=7)
            backend.seed(origin,'page',2,'<h1>Destination</h1>',user_id=7);self.backends[origin]=backend
        self.sites=CustomerSites(self.auth,self.root/'sites',lambda _:self.master,active_key_id='test-key',
            object_store=self.store,gateway_factory=self.factory)
        self.monitor=MonitoringService(self.sites,self.root/'monitor.sqlite',scanner=self.public_scan)
        self.application=GuardApplication(self.sites,self.monitor,authorized_test_origins=self.origins,
            scanner=self.public_scan,probe=lambda url,origin: url==origin+'/destination/',simulated_storage=True)
        self.site_a=self.application.connect(self.a,self.origins[0],'admin','synthetic-application-password')['site_id']
        self.site_b=self.application.connect(self.b,self.origins[1],'admin','synthetic-application-password')['site_id']

    def factory(self,origin,credentials):
        backend=self.backends[origin]
        class Gateway:
            def check(self):
                if credentials()!=('admin','synthetic-application-password'):raise PermissionError('Fixture authentication failed')
            def verify_site_owner(self):self.check();return 7
            def list_repair_resources(self,user_id):
                self.check()
                return [dict(resource_id=1,resource_type='post',link=origin+'/source/',slug='source',title='Source',status='publish'),
                        dict(resource_id=2,resource_type='page',link=origin+'/destination/',slug='destination',title='Destination',status='publish')]
            def read_authorized(self,*args):self.check();return backend.read_authorized(*args)
            def compare_and_swap(self,*args,**kwargs):self.check();return backend.compare_and_swap(*args,**kwargs)
        return Gateway()

    def public_scan(self,origin,*,page_limit,max_requests,start_url=None,before_request=lambda:None,checkpoint=lambda:None):
        links=set();discovered={};count=0
        def fetch(url,host,method='GET'):
            nonlocal count
            checkpoint();before_request();count+=1
            if '/missing-destination/' in url:
                if method=='HEAD':links.add(url)
                return 404,url,''
            kind,identifier=('page',2) if '/destination/' in url else ('post',1)
            content=self.backends[origin].read_authorized(origin,kind,identifier,7).content
            if method=='HEAD':links.add(url)
            html='<title>Fixture</title><meta name="description" content="Fixture">'+content
            return 200,url,'' if method=='HEAD' else html
        rows,broken,_,_=scan(start_url or origin,page_limit,fetcher=fetch,initial_validator=lambda url:target_url(url),
            max_links=1,link_observer=lambda link,source:discovered.setdefault(link,set()).add(source))
        return make_report(rows,broken,links,count,link_sources=discovered)

    def proposal(self,session=None,site=None,origin=None):
        session=session or self.a;site=site or self.site_a;origin=origin or self.origins[0]
        scan_record=self.application.scan(session,site,start_url=origin+'/source/',page_limit=1)
        option=self.application.proposals(session,site,scan_record['scan_id'])[0]
        return self.application.prepare_repair(session,site,scan_record['scan_id'],option['issue_key'],1,origin+'/destination/')

    def test_scanner_advisor_exact_proposal_backup_apply_restore_monitoring_and_alerts(self):
        review=self.proposal()
        self.assertIn('missing-destination',review['diff']);self.assertIn('/destination/',review['diff'])
        with self.assertRaises(PermissionError):self.application.approve_and_apply(self.a,self.site_a,review['plan_id'])
        result=self.application.approve_and_apply(self.a,self.site_a,review['plan_id'],confirmed=True)
        self.assertEqual(result['status'],'applied');self.assertIn('verified_snapshot',result)
        self.assertTrue(self.store.objects)
        record=self.application.scan(self.a,self.site_a,start_url=self.origins[0]+'/source/',page_limit=1)
        self.assertEqual(record['report']['broken'],[])
        self.monitor.configure(self.a,self.site_a,enabled=True,page_limit=1,max_requests=3)
        self.assertEqual(self.monitor.run_once()['status'],'complete')
        restore=self.application.prepare_restore(self.a,self.site_a,review['plan_id'])
        self.assertIn('missing-destination',restore['proposed_content'])
        restored=self.application.approve_and_apply(self.a,self.site_a,restore['plan_id'],confirmed=True)
        self.assertEqual(restored['status'],'applied')

    def test_customer_and_site_isolation_with_identical_wordpress_ids(self):
        one=self.proposal();two=self.proposal(self.b,self.site_b,self.origins[1])
        for operation in (lambda:self.application.review(self.b,self.site_a,one['plan_id']),
                          lambda:self.application.review(self.b,self.site_b,one['plan_id']),
                          lambda:self.application.scan_record(self.b,self.site_b,self.application.scan_record(self.a,self.site_a)['scan_id'])):
            with self.assertRaises(PermissionError):operation()
        self.assertEqual(self.application.approve_and_apply(self.b,self.site_b,two['plan_id'],confirmed=True)['status'],'applied')
        self.assertIn('missing-destination',self.backends[self.origins[0]].read_authorized(self.origins[0],'post',1,7).content)

    def test_simulated_corrupt_backup_blocks_write_and_requires_new_explicit_review(self):
        review=self.proposal();self.store.fail='corrupt'
        with self.assertRaises(EncryptedBackupError):self.application.approve_and_apply(self.a,self.site_a,review['plan_id'],confirmed=True)
        self.store.fail=None
        fresh=self.application.renew_review(self.a,self.site_a,review['plan_id'])
        self.assertNotEqual(fresh['plan_id'],review['plan_id'])
        self.assertEqual(self.application.approve_and_apply(self.a,self.site_a,fresh['plan_id'],confirmed=True)['status'],'applied')

    def test_new_login_recovers_history_but_cannot_reuse_old_approval(self):
        review=self.proposal();result=self.application.approve_and_apply(self.a,self.site_a,review['plan_id'],confirmed=True)
        self.auth.logout(self.a)
        new_session=self.auth.login('alice','Alice-unified-password')
        reopened=GuardApplication(self.sites,self.monitor,authorized_test_origins=self.origins,scanner=self.public_scan,
            probe=lambda *_:True,simulated_storage=True)
        self.assertEqual(reopened.history(new_session,self.site_a)[0]['repair']['result'],result)
        restore=reopened.prepare_restore(new_session,self.site_a,review['plan_id'])
        self.assertEqual(reopened.approve_and_apply(new_session,self.site_a,restore['plan_id'],confirmed=True)['status'],'applied')

    def test_later_edit_cannot_be_overwritten_by_manual_restore(self):
        review=self.proposal();self.application.approve_and_apply(self.a,self.site_a,review['plan_id'],confirmed=True)
        backend=self.backends[self.origins[0]];current=backend.read_authorized(self.origins[0],'post',1,7)
        backend.compare_and_swap(current,current.content,7,operation_id='concurrent-version')
        with self.assertRaises(RevisionMismatchError):self.application.prepare_restore(self.a,self.site_a,review['plan_id'])

    def test_missing_storage_and_expired_session_are_blocked(self):
        review=self.proposal();self.sites.object_store=None
        with self.assertRaises(PermissionError):self.application.approve_and_apply(self.a,self.site_a,review['plan_id'],confirmed=True)
        self.auth.logout(self.a)
        with self.assertRaises(AuthenticationError):self.application.scan(self.a,self.site_a)

    def test_controller_never_enables_real_customer_origins(self):
        with self.assertRaises(ValueError):GuardApplication(self.sites,self.monitor,authorized_test_origins=['https://example.com'])
        disabled=GuardApplication(self.sites,self.monitor)
        with self.assertRaises(PermissionError):disabled.connect(self.a,self.origins[0],'admin','synthetic')

    def test_arbitrary_issue_or_unreachable_replacement_cannot_produce_repair(self):
        record=self.application.scan(self.a,self.site_a,start_url=self.origins[0]+'/source/',page_limit=1)
        with self.assertRaises(UnsupportedRepair):self.application.prepare_repair(self.a,self.site_a,record['scan_id'],'forged',1,self.origins[0]+'/destination/')
        self.application.probe=lambda *_:False
        option=self.application.proposals(self.a,self.site_a,record['scan_id'])[0]
        with self.assertRaises(UnsupportedRepair):self.application.prepare_repair(self.a,self.site_a,record['scan_id'],option['issue_key'],1,self.origins[0]+'/destination/')
        with self.assertRaises(ValueError):replace_broken_href('<a href="/old">x</a>',self.origins[0]+'/source/',self.origins[0]+'/old','https://other.test/new')


class ExactLinkRepairTests(unittest.TestCase):
    def test_only_href_value_changes_preserving_markup_and_unicode(self):
        original='<p>Știință</p><a data-label="keep" href="/broken?a=1&amp;b=2">same text</a>'
        result=replace_broken_href(original,'https://fixture.test/source/','https://fixture.test/broken?a=1&b=2','https://fixture.test/destination/')
        self.assertEqual(result,'<p>Știință</p><a data-label="keep" href="https://fixture.test/destination/">same text</a>')

    def test_no_script_text_or_nonmatching_anchor_is_changed(self):
        with self.assertRaises(UnsupportedRepair):replace_broken_href('<script>"<a href=\"/old\">"</script>',
            'https://fixture.test/source/','https://fixture.test/old','https://fixture.test/new')
