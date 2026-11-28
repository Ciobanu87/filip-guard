"""Do not turn server/auth failures into content repairs or invent root causes."""
import unittest
from unittest.mock import patch
from wordpress_repair_diagnosis import diagnose_link
from guard_application import UnsupportedRepair,verify_public_replacement
import test_guard_application as fixture


class RepairDiagnosisTests(unittest.TestCase):
    def test_only_unambiguous_missing_responses_admit_replacement(self):
        for statuses,eligible in (([404],True),([410],True),([404,410],True),([403],False),([429],False),([500],False),([404,503],False),(['404'],False),([],False)):
            result=diagnose_link({'broken':[{'link':'https://example.test/old','status':s} for s in statuses]},'https://example.test/old')
            self.assertIs(result['link_replacement_eligible'],eligible)
            self.assertFalse(result['root_cause_confirmed']);self.assertTrue(result['requires_human_review'])
    def test_transient_or_forbidden_findings_remain_visible_but_offer_no_repair(self):
        f=fixture.UnifiedFlowTests();f.setUp();self.addCleanup(f.doCleanups)
        scan=f.application.scan(f.a,f.site_a,start_url=f.origins[0]+'/source/',page_limit=1)
        for status in (401,403,429,500,503):
            with f.application.db(f.a,f.site_a) as db:
                import json
                report=scan['report'];report['broken'][0]['status']=status
                db.execute('UPDATE application_scans SET report=? WHERE scan_id=?',(json.dumps(report),scan['scan_id']))
            self.assertEqual(f.application.proposals(f.a,f.site_a,scan['scan_id']),[])
            self.assertTrue(f.application.scan_record(f.a,f.site_a,scan['scan_id'])['report']['findings'])
    def test_stale_scan_cannot_prepare_new_repair(self):
        f=fixture.UnifiedFlowTests();f.setUp();self.addCleanup(f.doCleanups)
        scan=f.application.scan(f.a,f.site_a,start_url=f.origins[0]+'/source/',page_limit=1)
        option=f.application.proposals(f.a,f.site_a,scan['scan_id'])[0]
        with f.application.db(f.a,f.site_a) as db:db.execute('UPDATE application_scans SET created_at=created_at-901')
        with self.assertRaises(UnsupportedRepair):f.application.prepare_repair(f.a,f.site_a,scan['scan_id'],option['issue_key'],1,f.origins[0]+'/destination/')
    def test_replacement_failure_at_approval_prevents_backup_and_write(self):
        f=fixture.UnifiedFlowTests();f.setUp();self.addCleanup(f.doCleanups);review=f.proposal()
        f.application.probe=lambda *_:False
        with self.assertRaises(UnsupportedRepair):f.application.approve_and_apply(f.a,f.site_a,review['plan_id'],confirmed=True)
        self.assertEqual(f.store.objects,{});self.assertEqual(f.backends[f.origins[0]].read_authorized(f.origins[0],'post',1,7).revision,'1')
    def test_non_html_partial_or_empty_success_is_not_a_replacement_page(self):
        from types import SimpleNamespace
        for status,media in ((204,'text/html'),(206,'text/html'),(200,'application/json'),(200,None),(200,'text/html')):
            result=SimpleNamespace(status=status,body=b'',headers=[] if media is None else [('content-type',media)])
            with patch('guard_application._https_request_exchange',return_value=b''),patch('guard_application.parse_http_response',return_value=result):
                with self.assertRaises(UnsupportedRepair):verify_public_replacement('https://example.test/new','https://example.test')

    def test_inert_and_raw_text_anchors_are_not_modified(self):
        from guard_application import replace_broken_href
        source='https://example.test/source';old='https://example.test/old';new='https://example.test/new'
        for tag in ('textarea','title','xmp','iframe','noembed','noframes','template','noscript'):
            inert='<'+tag+'><a href="/old">literal</a></'+tag+'>'
            with self.subTest(tag=tag):
                with self.assertRaises(UnsupportedRepair):replace_broken_href(inert,source,old,new)
                self.assertEqual(replace_broken_href(inert+'<a href="/old">real</a>',source,old,new),inert+'<a href="'+new+'">real</a>')
    def test_base_and_plaintext_context_require_manual_review(self):
        from guard_application import replace_broken_href
        for prefix in ('<base href="https://other.test/">','<plaintext>'):
            with self.assertRaises(UnsupportedRepair):replace_broken_href(prefix+'<a href="/old">x</a>','https://example.test','https://example.test/old','https://example.test/new')

    def test_expired_scan_at_approval_blocks_repair_without_probing_or_backup(self):
        f=fixture.UnifiedFlowTests();f.setUp();self.addCleanup(f.doCleanups);review=f.proposal()
        with f.application.db(f.a,f.site_a) as db:db.execute('UPDATE application_scans SET created_at=created_at-901')
        with patch.object(f.application,'probe') as probe:
            with self.assertRaises(UnsupportedRepair):f.application.approve_and_apply(f.a,f.site_a,review['plan_id'],confirmed=True)
            probe.assert_not_called()
        self.assertEqual(f.store.objects,{})

    def test_replayed_or_previous_session_plan_is_blocked_before_url_probe(self):
        f=fixture.UnifiedFlowTests();f.setUp();self.addCleanup(f.doCleanups);review=f.proposal()
        fresh=f.auth.login('alice','Alice-unified-password')
        with patch.object(f.application,'probe') as probe:
            with self.assertRaises(PermissionError):f.application.approve_and_apply(fresh,f.site_a,review['plan_id'],confirmed=True)
            probe.assert_not_called()
        f.application.approve_and_apply(f.a,f.site_a,review['plan_id'],confirmed=True)
        with patch.object(f.application,'probe') as probe:
            with self.assertRaises(PermissionError):f.application.approve_and_apply(f.a,f.site_a,review['plan_id'],confirmed=True)
            probe.assert_not_called()
