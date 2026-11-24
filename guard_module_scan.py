"""Compose independent guards with Website Guard under one existing budget."""
from dataclasses import replace
import time
from monitoring_scan import MonitoringReport,SecureMonitoringScan,MonitoringLimit,MonitoringCancelled
from guard_module_contract import configure
from guard_network import GuardNetwork
import commerce_guard
import api_app_guard
import infrastructure_guard

REGISTRY={'commerce':commerce_guard.run,'api':api_app_guard.run,'infrastructure':infrastructure_guard.run}


class GuardModuleScan:
    def __init__(self,settings,*,website=None,network_factory=GuardNetwork,min_gap=1,max_seconds=60):
        if not 0<=min_gap<=5 or not 1<=max_seconds<=60:raise ValueError('Bounded module scan required')
        self.settings=settings;self.website=website if website is not None else SecureMonitoringScan()
        self.network_factory=network_factory;self.gap=min_gap;self.seconds=max_seconds

    def __call__(self,origin,*,page_limit=5,max_requests=20,before_request=lambda:None,checkpoint=lambda:None):
        if type(max_requests) is not int or not 1<=max_requests<=60:raise ValueError('Bounded request budget required')
        settings=configure(origin,self.settings);began=time.monotonic();count=0;last=None
        def bounded_checkpoint():
            checkpoint()
            if time.monotonic()-began>=self.seconds:raise MonitoringLimit('Shared guard deadline exhausted')
        def reserve():
            nonlocal count,last
            bounded_checkpoint()
            if count>=max_requests:raise MonitoringLimit('Shared guard request budget exhausted')
            if last is not None:
                delay=self.gap-(time.monotonic()-last)
                if delay>0:
                    if time.monotonic()+delay-began>=self.seconds:raise MonitoringLimit('Shared guard deadline exhausted')
                    time.sleep(delay)
            before_request();bounded_checkpoint();count+=1;last=time.monotonic()
        base=MonitoringReport((),(),(),(),(),True,0)
        if settings['website']:
            try:
                base=self.website(origin,page_limit=page_limit,max_requests=max_requests,
                                  before_request=reserve,checkpoint=bounded_checkpoint)
            except MonitoringCancelled:raise
            except Exception:base=replace(base,complete=False)
        context=self.network_factory(origin,before_request=reserve,checkpoint=bounded_checkpoint,
                                     max_seconds=max(.001,self.seconds-(time.monotonic()-began)))
        checks=[];findings=list(base.findings);scope=set(base.scope);complete=base.complete
        for name,runner in REGISTRY.items():
            if name not in settings:continue
            for check in runner(context,settings[name]):
                checkpoint();checks.append(check.as_dict())
                if check.status in ('pass','fail'):scope.add((name+':'+check.code,check.url))
                else:complete=False
                if check.status=='fail':
                    if len(findings)<200:findings.append(check.finding())
                    else:complete=False
        checkpoint()
        return replace(base,findings=tuple(findings),scope=tuple(sorted(scope)),complete=complete,
                       requests=count,module_checks=tuple(checks))
