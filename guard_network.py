"""Bounded read-only network capability shared by guards; no auth or redirects."""
import json
import ssl
import time
from monitoring_scan import target_url,MonitoringLimit
from wordpress_secure_https import _https_request_exchange,parse_http_response,resolve_public_ips,create_verified_connection


class GuardNetwork:
    def __init__(self,origin,*,before_request=lambda:None,checkpoint=lambda:None,max_seconds=60,clock=time.monotonic):
        self.host=target_url(origin)[0];self.origin=origin;self.reserve=before_request;self.checkpoint=checkpoint
        self.clock=clock;self.deadline=clock()+max_seconds;self.requests=0

    def slot(self):
        self.checkpoint()
        if self.clock()>=self.deadline:raise MonitoringLimit('Module deadline exhausted')
        self.reserve();self.checkpoint()
        remaining=self.deadline-self.clock()
        if remaining<=0:raise MonitoringLimit('Module deadline exhausted')
        self.requests+=1
        return min(8,remaining)

    def get(self,url,*,authority=False):
        host,path,_=target_url(url,None if authority else self.host)
        timeout=self.slot()
        response=parse_http_response(_https_request_exchange(host,path,timeout,
            headers=(('User-Agent','FilipGuardModules/1.0'),),accept='application/json,application/rdap+json,text/html'))
        if response.status==206 or 300<=response.status<400:raise ValueError('Partial responses and redirects are not accepted')
        if len(response.body)>1_500_000:raise ValueError('Module response exceeds bound')
        # Do not store cookies, authorization, bodies or sensitive headers.
        types=[v.lower().split(';')[0].strip() for k,v in response.headers if k=='content-type']
        if len(types)>1:raise ValueError('Ambiguous response type')
        return response.status,(types[0] if types else ''),response.body

    def site(self,path):return self.get(self.origin+path)

    def dns(self):
        addresses=resolve_public_ips(self.host,timeout=self.slot())
        if len(addresses)>64:raise ValueError('DNS observation bound exceeded')
        return addresses

    def certificate_expiry(self):
        connection=create_verified_connection(self.host,timeout=self.slot())
        try:return ssl.cert_time_to_seconds(connection.getpeercert()['notAfter'])
        finally:connection.close()

    @staticmethod
    def json(body):
        def pairs(items):
            result={}
            for key,value in items:
                if key in result:raise ValueError('Duplicate JSON key')
                result[key]=value
            return result
        return json.loads(body.decode('utf-8'),object_pairs_hook=pairs,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('Invalid JSON number')))
