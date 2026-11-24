"""Versioned read-only module contract; trusted registry, never user code/tools.

A future guard may implement run(context, config), but no AI Agent Guard exists.
Only explicitly registered, owner-configured modules can run today.
"""
from dataclasses import dataclass
from hashlib import sha256
import ipaddress
import json
import re
from urllib.parse import unquote,urlsplit
from advisor_context import clean
from monitoring_scan import target_url

CONTRACT_VERSION='read-only-guard-v1'
MODULES=('commerce','api','infrastructure')


def path(value):
    if type(value) is not str or not 1<=len(value)<=512 or not value.startswith('/') or value.startswith('//'):
        raise ValueError('A bounded same-site public path is required')
    decoded=unquote(unquote(value))
    if (any(c in decoded for c in '?#\\') or re.search(r'[\x00-\x20\x7f]',decoded)
            or any(part in ('.','..') for part in decoded.split('/')) or clean(decoded,2048)!=decoded
            or re.search(r'(^|/)(wp-admin|wp-login\.php|login|logout|signout|cart|checkout|add-to-cart|delete|remove|update|action)(/|$)',decoded,re.I)):
        raise ValueError('Only public read-only paths without secrets/actions/query strings are allowed')
    target_url('https://validation.example'+value)
    return value


def paths(values):
    if type(values) is not list or not 1<=len(values)<=3 or any(type(value) is not str for value in values) or len(set(values))!=len(values):
        raise ValueError('One to three distinct public paths required')
    return [path(value) for value in values]


def configure(origin,settings):
    host,_,canonical=target_url(origin)
    if origin!='https://'+host:raise ValueError('Canonical authorized origin required')
    if type(settings) is not dict or set(settings)-({'website'}|set(MODULES)):
        raise ValueError('Unknown module; dynamic code and AI Agent Guard are not supported')
    result={'website':settings.get('website',True)}
    if type(result['website']) is not bool:raise ValueError('Website selection must be boolean')
    for name in MODULES:
        item=settings.get(name)
        if item is None:continue
        if type(item) is not dict:raise ValueError('Bounded module settings required')
        if name=='commerce':
            if set(item)-{'paths','require_product','expected_currency'}:raise ValueError('Unknown Commerce setting')
            require=item.get('require_product',False);currency=item.get('expected_currency')
            if type(require) is not bool or (currency is not None and (type(currency) is not str or not re.fullmatch('[A-Z]{3}',currency))):
                raise ValueError('Invalid product expectations')
            result[name]={'paths':paths(item.get('paths')),'require_product':require,'expected_currency':currency}
        elif name=='api':
            if set(item)-{'paths','statuses','require_json','required_keys','json_equals'}:raise ValueError('Unknown API setting')
            statuses=item.get('statuses',[200]);keys=item.get('required_keys',[]);require=item.get('require_json',True)
            if (type(statuses) is not list or not 1<=len(statuses)<=5 or any(type(v) is not int or not 200<=v<=599 or v==206 or 300<=v<400 for v in statuses)
                    or len(set(statuses))!=len(statuses) or type(require) is not bool or type(keys) is not list or len(keys)>8
                    or any(type(k) is not str or not re.fullmatch('[A-Za-z][A-Za-z0-9_-]{0,39}',k)
                           or re.search('secret|token|password|credential|authorization|cookie|session|key',k,re.I) for k in keys)
                    or len(set(keys))!=len(keys) or (keys and not require)):
                raise ValueError('Invalid public API expectations; credentials are not supported')
            expected=item.get('json_equals',{})
            if (type(expected) is not dict or len(expected)>1 or (expected and not require)
                    or any(type(k) is not str or not re.fullmatch('[A-Za-z][A-Za-z0-9_-]{0,39}',k) or re.search('secret|token|password|credential|authorization|cookie|session|key',k,re.I) for k in expected)
                    or any(type(v) not in (str,bool,int) or (type(v) is str and (len(v)>80 or clean(v,80)!=v)) or (type(v) is int and abs(v)>1000000000) for v in expected.values())):
                raise ValueError('Only bounded nonsecret public health expectations are supported')
            result[name]={'paths':paths(item.get('paths')),'statuses':statuses,'require_json':require,'required_keys':keys,'json_equals':dict(expected)}
        else:
            if set(item)-{'expected_ips','warn_days','registered_domain'}:raise ValueError('Unknown infrastructure setting')
            addresses=item.get('expected_ips',[]);days=item.get('warn_days',30);domain=item.get('registered_domain')
            if type(addresses) is not list or len(addresses)>8 or any(type(v) is not str or '%' in v or not ipaddress.ip_address(v).is_global for v in addresses):
                raise ValueError('Expected DNS addresses must be public')
            if type(days) is not int or not 1<=days<=90:raise ValueError('Expiry warning must be 1–90 days')
            if domain is not None:
                if type(domain) is not str:raise ValueError('Explicit registered domain required')
                parsed,_,_=target_url('https://'+domain)
                if parsed!=domain or not (host==domain or host.endswith('.'+domain)) or domain.count('.')<1:
                    raise ValueError('Registered domain must contain the authorized site')
            result[name]={'expected_ips':sorted({str(ipaddress.ip_address(value)) for value in addresses}),'warn_days':days,'registered_domain':domain}
    if not result['website'] and not any(name in result for name in MODULES):raise ValueError('At least one guard is required')
    return result


@dataclass(frozen=True)
class Check:
    module:str
    code:str
    url:str
    status:str
    problem:str
    solution:str
    priority:str='Medium'
    evidence:tuple=()

    def as_dict(self):
        if self.module not in MODULES or self.status not in ('pass','fail','unknown','unsupported'):
            raise ValueError('Invalid read-only module result')
        return dict(module=self.module,code=self.code,page=self.url,status=self.status,problem=self.problem,
                    solution=self.solution,priority=self.priority,evidence=list(self.evidence),autofix=False,
                    contract_version=CONTRACT_VERSION)

    def finding(self):
        data=self.as_dict();kind=self.module+':'+self.code
        key=sha256(json.dumps([CONTRACT_VERSION,kind,self.url],separators=(',',':')).encode()).hexdigest()
        return dict(key=key,scope_kind=kind,scope_key=self.url,reason=self.problem,
                    risk='Verify the observed condition before any separately authorized change.',**data)


def defaults(kind=None):
    if kind=='api':return {'website':False,'api':{'paths':['/'],'statuses':[200],'require_json':False,'required_keys':[],'json_equals':{}}}
    if kind=='commerce':return {'website':False,'commerce':{'paths':['/'],'require_product':False,'expected_currency':None}}
    if kind=='infrastructure':return {'website':False,'infrastructure':{'expected_ips':[],'warn_days':30,'registered_domain':None}}
    return {'website':True}
