"""Verified public DNS/TLS and opt-in registry expiry; no infrastructure changes."""
from datetime import datetime,timezone
import time
from urllib.parse import urlsplit
from guard_module_contract import Check
from monitoring_scan import target_url

BOOTSTRAP='https://data.iana.org/rdap/dns.json'


def registration_expiry(context,domain):
    status,kind,body=context.get(BOOTSTRAP,authority=True)
    if status!=200:raise ValueError('IANA bootstrap unavailable')
    data=context.json(body);matches=[]
    for entry in data.get('services',[])[:2000]:
        if type(entry) is not list or len(entry)!=2:continue
        labels,urls=entry
        if type(labels) is not list or type(urls) is not list:continue
        for label in labels:
            if type(label) is str and (domain==label or domain.endswith('.'+label)):
                for base in urls:
                    if type(base) is str and base.startswith('https://'):matches.append((len(label.split('.')),base))
    if not matches:raise ValueError('Authoritative secure RDAP service unavailable')
    base=sorted(matches,key=lambda item:-item[0])[0][1];p=urlsplit(base)
    if p.query or p.fragment or not p.path.endswith('/'):raise ValueError('Invalid authoritative RDAP base')
    target_url(base)
    status,kind,body=context.get(base+'domain/'+domain,authority=True)
    if status!=200:raise ValueError('Registry response unavailable')
    data=context.json(body)
    if data.get('objectClassName')!='domain' or str(data.get('ldhName','')).lower().rstrip('.')!=domain:
        raise ValueError('Registry domain identity mismatch')
    dates=[]
    for event in data.get('events',[])[:100]:
        if type(event) is dict and event.get('eventAction')=='expiration':
            date=datetime.fromisoformat(event['eventDate'].replace('Z','+00:00'))
            if date.tzinfo is None:raise ValueError('Timezone-aware registry expiry required')
            dates.append(date.timestamp())
    if len(set(dates))!=1:raise ValueError('Unambiguous registry expiration date unavailable')
    return dates[0]


def run(context,config,*,now=None):
    now=time.time() if now is None else now;url=context.origin+'/'
    try:
        addresses=context.dns();expected=config['expected_ips'];valid=not expected or set(addresses)==set(expected)
        yield Check('infrastructure','dns',url,'pass' if valid else 'fail',
            'Public A/AAAA addresses meet configured expectations.' if valid else 'Observed DNS addresses differ from the configured baseline.',
            'Verify intended DNS/CDN changes with the domain operator; do not automatically replace records.',
            evidence=tuple(('address',address) for address in addresses))
    except Exception:
        yield Check('infrastructure','dns',url,'unknown','Public DNS verification failed.',
            'Check DNS availability and public address routing. Private/mixed answers remain blocked.')
    try:
        expiry=context.certificate_expiry();days=(expiry-now)/86400;valid=days>config['warn_days']
        yield Check('infrastructure','tls-expiry',url,'pass' if valid else 'fail',
            'Verified TLS certificate is outside the warning window.' if valid else 'Verified TLS certificate approaches expiration.',
            'Review renewal and certificate deployment with the authorized operator.','High',(('expires_at',expiry),))
    except Exception:
        yield Check('infrastructure','tls-expiry',url,'unknown','TLS identity/expiry could not be verified.',
            'Check certificate validity, hostname and chain. Never disable certificate validation.')
    domain=config['registered_domain']
    if domain:
        try:
            expiry=registration_expiry(context,domain);valid=(expiry-now)/86400>config['warn_days']
            yield Check('infrastructure','domain-expiry',url,'pass' if valid else 'fail',
                'Registry expiration is outside the warning window.' if valid else 'Registry domain expiration requires review.',
                'Confirm renewal and account status with the registrar; registry dates alone do not guarantee service continuity.',
                'High',(('registered_domain',domain),('expires_at',expiry)))
        except Exception:
            yield Check('infrastructure','domain-expiry',url,'unknown','Authoritative registration expiry is unavailable.',
                'Confirm the registered apex and registry/registrar status manually; no expiration date is guessed.')
