"""Public UI orchestration through existing pinned HTTPS and bounded Scanner.

No credentials, redirects, mutation, AI invocation or ambient requests client.
"""
import re
import time
from urllib.parse import urlsplit
from wordpress_secure_https import _https_request_exchange,parse_http_response
from wordpress_public_readonly import fetch_public_wordpress


def secure_public_fetch(url,host,method='GET',*,timeout=8):
    from monitoring_scan import target_url
    from website_scanner import MAX_BYTES
    if method not in ('GET','HEAD'):raise ValueError('Read-only page check required')
    hostname,path,canonical=target_url(url,host)
    # Like the existing monitoring reader, a logical HEAD uses one bounded GET.
    try:
        raw=_https_request_exchange(hostname,path,timeout,headers=(('User-Agent','FilipGuardAudit/1.0'),),accept='text/html,application/xhtml+xml')
        response=parse_http_response(raw)
    except (OSError,ValueError):raise ValueError('Verified HTTPS page read failed') from None
    if response.status==206 or 300<=response.status<400:raise ValueError('Partial responses and redirects are blocked')
    if len(response.body)>MAX_BYTES:raise ValueError('Public page too large')
    types=[value for name,value in response.headers if name=='content-type']
    if len(types)>1:raise ValueError('Ambiguous page content type')
    text=''
    if method=='GET' and types and types[0].lower().split(';')[0].strip() in ('text/html','application/xhtml+xml'):
        charset=re.search(r'charset\s*=\s*[\"\']?([A-Za-z0-9_-]+)',types[0],re.I)
        try:text=response.body.decode(charset.group(1) if charset else 'utf-8',errors='replace')
        except LookupError:raise ValueError('Unsupported page encoding') from None
    return response.status,canonical,text


def run_public_scan(start,page_limit):
    from monitoring_scan import SecureMonitoringScan,target_url
    if not urlsplit(start).scheme:start='https://'+start
    hostname,_,canonical=target_url(start)
    report=SecureMonitoringScan(max_seconds=60,min_gap=0)(
        'https://'+hostname,start_url=canonical,page_limit=page_limit,max_requests=60)
    return {'start_url':canonical,'rows':list(report.rows),'broken':list(report.broken),
            'contexts':{page:list(text) for page,text in report.page_context},'complete':report.complete,
            'checked':sum(kind=='link' for kind,_ in report.scope),'discovered':len(report.discovered_links),
            'requests':report.requests}


class _Budget:
    def __init__(self,max_seconds=20,max_requests=8,clock=time.monotonic):
        self.clock=clock;self.deadline=clock()+max_seconds;self.remaining=max_requests
    def slot(self):
        remaining=self.deadline-self.clock()
        if self.remaining<=0 or remaining<=0:raise ValueError('Public suggestion budget exhausted')
        self.remaining-=1;return min(8,remaining)


def public_wordpress_items(hostname,*,budget=None):
    from monitoring_scan import target_url
    budget=budget or _Budget();items=[]
    try:
        for resource in ('posts','pages'):
            batch=fetch_public_wordpress(hostname,resource,per_page=30,timeout=budget.slot())
            if type(batch) is not list or len(batch)>30:raise ValueError('Bounded public inventory required')
            for item in batch:
                target_url(item['link'],hostname)
                items.append(item)
        return items
    except (OSError,ValueError,KeyError,TypeError):return []


def verified_wordpress_suggestions(broken):
    from monitoring_scan import target_url
    from link_resolver import suggest_replacements
    if not broken:return []
    result=[]
    try:
        hostname,_,_=target_url(broken[0]['link'])
        budget=_Budget();items=public_wordpress_items(hostname,budget=budget)
        if not items:return []
        checked={}
        for issue in broken[:5]:
            target_url(issue['link'],hostname)
            for match in suggest_replacements(issue['link'],items,limit=3):
                candidate=match['candidate_url']
                if candidate not in checked:
                    checked[candidate]=secure_public_fetch(candidate,hostname,'HEAD',timeout=budget.slot())[0]
                if 200<=checked[candidate]<300:result.append({**match,'verified':True,'requires_review':True})
        return result
    except (OSError,ValueError,KeyError,TypeError):return result
