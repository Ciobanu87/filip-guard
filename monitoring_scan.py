"""Read-only monitoring built on the shared Scanner and existing rule Advisor.

Only unauthenticated HTTPS GET is possible. No credentials, repair engine or
WordPress mutation endpoints are imported or invoked by this module.
"""
from dataclasses import dataclass
from hashlib import sha256
import ipaddress
import json
import re
import time
from urllib.parse import urlsplit, urlunsplit, quote

import requests
from ai_advisor import analyze_pages
from website_scanner import scan, MAX_BYTES
from wordpress_secure_https import _https_request_exchange, parse_http_response, _validate_request
from wordpress_execution_gate import _origin


class MonitoringCancelled(RuntimeError): pass
class MonitoringLimit(ValueError): pass


def target_url(value, host=None):
    if type(value) is not str or len(value)>2048 or re.search(r'[\x00-\x20\x7f\\]',value):
        raise ValueError('Invalid monitoring URL')
    p=urlsplit(value)
    if (p.scheme!='https' or not p.hostname or p.username is not None or p.password is not None
            or p.port not in (None,443) or p.fragment):
        raise ValueError('Only the authorized HTTPS site can be monitored')
    origin='https://'+_origin('https://'+p.netloc)
    hostname=urlsplit(origin).hostname
    if host is not None and hostname!=host.lower().rstrip('.'):
        raise ValueError('External monitoring destination blocked')
    try:
        address=ipaddress.ip_address(hostname)
    except ValueError:
        if hostname=='localhost' or hostname.endswith('.localhost'):
            raise ValueError('Private monitoring destination blocked')
    else:
        if not address.is_global:raise ValueError('Private monitoring destination blocked')
    path=quote(p.path or '/',safe="/:@-._~!$&'()*+,;=%")
    if p.query:path+='?'+quote(p.query,safe="=&/:@-._~!$'()*+,;%")
    _validate_request(hostname,path,8)
    return hostname,path,urlunsplit(('https',hostname,p.path or '/',p.query,''))


@dataclass(frozen=True)
class MonitoringReport:
    rows: tuple
    broken: tuple
    recommendations: tuple
    findings: tuple
    scope: tuple
    complete: bool
    requests: int
    discovered_links: tuple = ()
    page_context: tuple = ()


def _text(value,limit=1000):
    return ''.join(c for c in str(value) if ord(c)>=32 and ord(c)!=127)[:limit]


def make_report(rows,broken,checked_links,requests_count,complete=True,link_sources=None,page_context=None):
    safe_rows=[];scope=set()
    for row in rows:
        item={key:_text(value,2048 if key=='page' else 1000) if isinstance(value,str) else value for key,value in row.items()}
        safe_rows.append(item)
        status=item.get('http_status');page=item.get('page','')
        if type(status) is int:
            scope.add(('http',page))
            if 200<=status<300 and item.get('issues')!='Non-HTML or empty page':
                scope.add(('seo',page));scope.add(('source',page))
        else:complete=False
    recommendations=analyze_pages(safe_rows);findings=[]
    for recommendation in recommendations:
        problem=recommendation['problem'];page=recommendation['page']
        # Network failures are monitoring errors, not proof an old SEO issue resolved.
        row=next((r for r in safe_rows if r.get('page')==page),{})
        if type(row.get('http_status')) is not int:continue
        kind='http' if problem=='Page unavailable or scan failed' else 'seo'
        payload={**recommendation,'autofix':False}
        key=sha256(json.dumps([kind,page,problem],separators=(',',':')).encode()).hexdigest()
        findings.append(dict(key=key,scope_kind=kind,scope_key=page,**payload))
    safe_broken=[]
    for issue in broken:
        item={key:_text(value,2048) if isinstance(value,str) else value for key,value in issue.items()}
        safe_broken.append(item)
        if type(item.get('status')) is not int:
            complete=False;continue
        link=item['link'];key=sha256(json.dumps(['link',link],separators=(',',':')).encode()).hexdigest()
        findings.append(dict(key=key,scope_kind='link',scope_key=link,page=link,
            problem='Broken internal link',solution='Review and repair the link after explicit approval.',
            reason='Visitors may be unable to reach this destination.',risk='Review replacement relevance.',
            priority='High',autofix=False,sources=sorted((link_sources or {}).get(link,()))))
    scope.update(('link',url) for url in checked_links)
    return MonitoringReport(tuple(safe_rows),tuple(safe_broken),tuple(recommendations),tuple(findings),
                            tuple(sorted(scope)),bool(complete),requests_count,tuple(sorted(link_sources or {})),tuple((page,tuple(text)) for page,text in (page_context or {}).items()))


class SecureMonitoringScan:
    def __init__(self,*,max_seconds=60,min_gap=1):
        if not 1<=max_seconds<=60 or not 0<=min_gap<=5:raise ValueError('Invalid monitoring limits')
        self.max_seconds,self.min_gap=max_seconds,min_gap

    def __call__(self,origin,*,page_limit=5,max_requests=20,before_request=lambda:None,checkpoint=lambda:None,start_url=None):
        if type(page_limit) is not int or not 1<=page_limit<=30 or type(max_requests) is not int or not page_limit<=max_requests<=60:
            raise ValueError('Invalid monitoring scan bounds')
        hostname,_,_=target_url(origin)
        if 'https://'+hostname!=origin:raise ValueError('Canonical authorized site origin required')
        start=start_url or origin
        target_url(start,hostname)
        began=time.monotonic();last=None;count=0;cache={};links=set();limited=False;discovered={};contexts={}
        def fetch(url,host,method='GET'):
            nonlocal count,last,limited
            target,path,canonical=target_url(url,hostname)
            if host!=hostname:raise ValueError('Monitoring target mismatch')
            checkpoint()
            if canonical not in cache:
                remaining=self.max_seconds-(time.monotonic()-began)
                if count>=max_requests or remaining<=0:
                    limited=True;raise MonitoringLimit('Monitoring request/time budget exhausted')
                if last is not None:
                    pause=self.min_gap-(time.monotonic()-last)
                    if pause>0:
                        if pause>=remaining:limited=True;raise MonitoringLimit('Monitoring time budget exhausted')
                        time.sleep(pause)
                before_request();checkpoint()
                timeout=min(8,self.max_seconds-(time.monotonic()-began))
                if timeout<=0:limited=True;raise MonitoringLimit('Monitoring time budget exhausted')
                count+=1;last=time.monotonic()
                try:
                    raw=_https_request_exchange(target,path,timeout,headers=(('User-Agent','FilipGuardMonitor/0.1'),),
                        accept='text/html,application/xhtml+xml')
                    response=parse_http_response(raw)
                    if len(response.body)>MAX_BYTES:raise ValueError('Monitoring page too large')
                    types=[v for k,v in response.headers if k=='content-type']
                    if len(types)>1:raise ValueError('Ambiguous monitoring content type')
                    html=''
                    if types and types[0].lower().split(';')[0].strip() in ('text/html','application/xhtml+xml'):
                        charset=re.search(r'charset\s*=\s*[\"\']?([A-Za-z0-9_-]+)',types[0],re.I)
                        encoding=charset.group(1) if charset else 'utf-8'
                        try:html=response.body.decode(encoding,errors='replace')
                        except LookupError:raise ValueError('Unsupported monitoring charset') from None
                    cache[canonical]=(response.status,canonical,html)
                except (OSError,ValueError) as error:
                    raise requests.RequestException('Secure monitoring request failed') from None
            result=cache[canonical]
            if method=='HEAD':links.add(url)
            return result[0],result[1],'' if method=='HEAD' else result[2]
        rows,broken,_,_=scan(start,page_limit,fetcher=fetch,initial_validator=lambda url:target_url(url),
                            max_links=min(10,max_requests-page_limit),max_discovered=200,link_observer=lambda link,source:discovered.setdefault(link,set()).add(source),
                            context_observer=lambda page,text:contexts.update({page:text}))
        checkpoint()
        return make_report(rows,broken,links,count,not limited,discovered,contexts)
