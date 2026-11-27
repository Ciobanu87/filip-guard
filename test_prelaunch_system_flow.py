"""Disposable full flow: existing WordPress fixture plus four-module monitoring.

No real API/provider/SMTP/Oracle calls or production permission changes.
"""
import time
import unittest
from unittest.mock import patch
from guard_module_scan import GuardModuleScan
from monitoring_service import MonitoringService
from monitoring_scan import make_report
from contextual_advisor import ContextualAdvisor
from test_contextual_advisor import SimulatedProvider
import test_guard_application as fixtures


class PrelaunchSystemFlowTests(unittest.TestCase):
    def test_identify_advise_approve_backup_apply_partial_monitor_restore_and_isolate(self):
        clock=[10000.0]
        controlled=patch('customer_auth.time.time',side_effect=lambda:clock[0]);controlled.start();self.addCleanup(controlled.stop)
        fixture=fixtures.UnifiedFlowTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        app=fixture.application;origin=fixture.origins[0];state={'api':'bad'}
        def scan(*args,**kwargs):
            original=fixture.public_scan(*args,**kwargs)
            rows=[{**row,'meta_description':''} for row in original.rows]
            return make_report(rows,original.broken,[],original.requests,
                link_sources={origin+'/missing-destination/':{origin+'/source/'}},
                page_context={row['page']:['Public documentation for the sample installation and update process.'] for row in rows})
        app.scanner=scan
        record=app.scan(fixture.a,fixture.site_a,start_url=origin+'/source/',page_limit=1)
        provider=SimulatedProvider();engine=ContextualAdvisor(fixture.root/'evaluation.sqlite',provider)
        advice=app.advice(fixture.a,fixture.site_a,record['scan_id'],generate=True,advisor=engine)
        self.assertEqual(advice['status'],'model-assisted');self.assertEqual(provider.calls,1)
        self.assertTrue(all(not item['autofix'] and not item['repair_supported'] for item in advice['recommendations']))
        proposal=app.proposals(fixture.a,fixture.site_a,record['scan_id'])[0]
        review=app.prepare_repair(fixture.a,fixture.site_a,record['scan_id'],proposal['issue_key'],1,origin+'/destination/')
        with self.assertRaises(PermissionError):app.approve_and_apply(fixture.b,fixture.site_a,review['plan_id'],confirmed=True)
        with self.assertRaises(PermissionError):app.approve_and_apply(fixture.a,fixture.site_a,review['plan_id'])

        class Network:
            def __init__(self,origin,**kwargs):self.origin=origin
            def site(self,path):
                if path=='/health':
                    if state['api']=='unknown':raise OSError('private temporary fault')
                    return 200,'application/json',b'{"status":"error"}' if state['api']=='bad' else b'{"status":"ok"}'
                return 200,'text/html',b'<h1>Catalog</h1>'
            def json(self,body):
                import json
                return json.loads(body)
            def dns(self):return ['93.184.216.34']
            def certificate_expiry(self):return 4102444800
        monitor=MonitoringService(fixture.sites,fixture.root/'combined-monitor.sqlite',scanner=fixture.public_scan,
            module_runner=lambda settings,**kwargs:GuardModuleScan(settings,network_factory=Network,min_gap=0,**kwargs))
        base=clock[0];slots={};reserve=monitor.reserve_request
        def spaced(job,*,now=None):
            slots[now]=slots.get(now,now)+1
            return reserve(job,now=slots[now])
        monitor.configure_modules(fixture.a,fixture.site_a,{'website':True,'commerce':{'paths':['/catalog']},
            'api':{'paths':['/health'],'json_equals':{'status':'ok'}},'infrastructure':{}},now=base)
        monitor.configure(fixture.a,fixture.site_a,enabled=True,interval_seconds=900,page_limit=1,max_requests=10,now=base)
        with patch.object(monitor,'reserve_request',side_effect=spaced),patch('contextual_advisor.configured_advisor',side_effect=AssertionError('No background inference')):
            first=monitor.run_once(now=base);self.assertEqual(first['new'],2)
            applied=app.approve_and_apply(fixture.a,fixture.site_a,review['plan_id'],confirmed=True)
            self.assertEqual(applied['status'],'applied');self.assertTrue(fixture.store.objects)
            state['api']='unknown';clock[0]=base+900
            partial=monitor.run_once(now=base+900)
            self.assertEqual(partial['status'],'partial');self.assertEqual(partial['resolved'],1)
            state['api']='ok';clock[0]=base+1800
            recovered=monitor.run_once(now=base+1800);self.assertEqual(recovered['resolved'],1)
            fixture.a=fixture.auth.login('alice','Alice-unified-password')
            restore=app.prepare_restore(fixture.a,fixture.site_a,review['plan_id'])
            self.assertEqual(app.approve_and_apply(fixture.a,fixture.site_a,restore['plan_id'],confirmed=True)['status'],'applied')
            clock[0]=base+2700
            again=monitor.run_once(now=base+2700);self.assertEqual(again['new'],1)
        self.assertEqual(provider.calls,1)
        self.assertFalse(again['repairs_authorized'])
        clock[0]=base+2701;fixture.b=fixture.auth.login('bob','Bob-unified-password')
        with self.assertRaises(PermissionError):monitor.history(fixture.b,fixture.site_a,now=base+2701)
        self.assertEqual(monitor.notifications(fixture.b,now=base+2701),[])
        self.assertIn('missing-destination',fixture.backends[origin].read_authorized(origin,'post',1,7).content)
        self.assertIn('missing-destination',fixture.backends[fixture.origins[1]].read_authorized(fixture.origins[1],'post',1,7).content)
