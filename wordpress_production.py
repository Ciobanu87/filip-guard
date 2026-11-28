"""Disabled-by-default production integration of the existing exact-link engine."""
from collections import Counter
import json
import os
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from guard_application import GuardApplication,canonical,replace_broken_href,UnsupportedRepair,verify_public_replacement
from customer_auth import instant
from customer_sites import CustomerSites
from wordpress_revision_guard import ResourceSnapshot,verify_unchanged
from wordpress_rest_gateway import WordPressRESTGateway,WordPressRESTError
from wordpress_production_policy import read_production_policy
from wordpress_secure_https import _https_request_exchange,parse_http_response
from monitoring_scan import target_url


def require_production_content(content):
    import re
    from html import unescape
    from html.parser import HTMLParser
    from wordpress_compatibility import require_content_profile
    require_content_profile(content)
    if re.search(r'<\s*(?:base|plaintext|script|style|textarea|title|xmp|iframe|noembed|noframes|template|noscript)\b',content,re.I):
        raise PermissionError('Production content requires manual compatibility review')
    class QuotedAnchors(HTMLParser):
        def handle_starttag(self,tag,attrs):
            if tag!='a':return
            hrefs=[v for k,v in attrs if k=='href']
            if not hrefs:return
            quoted=list(re.finditer(r'''\bhref\s*=\s*(["'])(.*?)\1''',self.get_starttag_text(),re.I|re.S))
            if len(hrefs)!=1 or len(quoted)!=1 or unescape(quoted[0].group(2))!=hrefs[0]:
                raise PermissionError('Unambiguous quoted href profile required')
        handle_startendtag=handle_starttag
    parser=QuotedAnchors();parser.feed(content);parser.close()


def public_page(url):
    host,path,_=target_url(url)
    response=parse_http_response(_https_request_exchange(host,path,8,accept='text/html,application/xhtml+xml'))
    types=[v.split(';')[0].strip().lower() for k,v in response.headers if k.lower()=='content-type']
    if response.status!=200 or types not in (['text/html'],['application/xhtml+xml']) or not response.body.strip():
        raise ValueError('Independent public page unavailable')
    return response.body.decode('utf-8',errors='strict')


def anchor_counts(html,source):
    soup=BeautifulSoup(html,'html.parser');result=Counter()
    if soup.find('base') or soup.find('plaintext'):raise ValueError('Unreviewed public URL interpretation')
    for anchor in soup.find_all('a',href=True):
        if any(parent.name in ('script','style','textarea','title','xmp','iframe','noembed','noframes','template','noscript') for parent in anchor.parents):continue
        try:result[canonical(urljoin(source,anchor['href']))]+=1
        except ValueError:continue
    return result


def verify_rendered_change(original,written,source,selector,html):
    verify_unchanged(original,original);verify_unchanged(written,written)
    if (original.site_url,original.resource_type,original.resource_id)!=(written.site_url,written.resource_type,written.resource_id):raise ValueError('Public verification identity mismatch')
    before=anchor_counts(original.content,source);after=anchor_counts(written.content,source)
    changed={url for url in before.keys()|after.keys() if before[url]!=after[url]}
    if not changed:raise ValueError('No independently verifiable link change')
    soup=BeautifulSoup(html,'html.parser')
    if soup.find('base') or soup.find('plaintext'):raise ValueError('Unsupported public document context')
    selected=soup.select(selector.format(resource_id=written.resource_id))
    if len(selected)!=1:raise ValueError('Reviewed content container missing or ambiguous')
    observed=anchor_counts(str(selected[0]),source)
    if any(observed[url]!=after[url] for url in changed):raise ValueError('Public content does not reflect the approved link change')
    return True


class ProductionWordPressGateway(WordPressRESTGateway):
    def __init__(self,site_url,credentials,policy_provider):
        self.policy_provider=policy_provider
        if policy_provider().origin!=site_url:raise PermissionError('Production origin not admitted')
        super().__init__(site_url,credentials)
    def _policy(self):
        policy=self.policy_provider()
        if policy.origin!=self.site_url:raise PermissionError('Production admission changed')
        return policy
    def _request(self,*args,**kwargs):
        self._policy()
        return super()._request(*args,**kwargs)
    def _target(self,site,kind,resource_id,user_id):
        if not self._policy().permits(kind,resource_id):raise PermissionError('Production resource not admitted')
        return super()._target(site,kind,resource_id,user_id)
    def list_repair_resources(self,user_id):
        # Published destination candidates are read-only; mutation targets are
        # separately restricted by _target and the production controller.
        self._policy()
        return super().list_repair_resources(user_id)
    def compare_and_swap(self,expected,content,user_id,*,operation_id):
        path=self._target(expected.site_url,expected.resource_type,expected.resource_id,user_id)
        self._identity(user_id)
        _,data=self._request(path+'/compatibility')
        if data.get('protocol')!='filip-guard-compatibility-v1' or type(data.get('snapshot')) is not dict or type(data.get('evidence')) is not dict:
            raise WordPressRESTError('Fresh production inventory required')
        snapshot=self._snapshot(data['snapshot'],expected.resource_type,expected.resource_id,user_id)
        verify_unchanged(expected,snapshot)
        self._policy().check_evidence(snapshot,{**data['evidence'],'site_url':self.site_url})
        return super().compare_and_swap(expected,content,user_id,operation_id=operation_id)


class ProductionCustomerSites(CustomerSites):
    def __init__(self,*args,policy_provider,**kwargs):
        self.policy_provider=policy_provider
        super().__init__(*args,**kwargs)
    def _context(self,session,site_id,*,now=None,require_external=False):
        engine,identity,row=super()._context(session,site_id,now=now,require_external=require_external)
        workspace=self._workspace(self.auth.resolve(session,now=now),site_id)
        def flow(plan_id):
            self._owned(session,site_id)
            policy=self.policy_provider()
            if policy.origin!=row['origin']:raise PermissionError('Production site not admitted')
            path=workspace/'application.sqlite'
            from runtime_state import require_existing_database
            require_existing_database(path,{'application_repairs','application_scans'})
            import sqlite3
            with sqlite3.connect(path) as db:
                db.row_factory=sqlite3.Row
                record=db.execute('SELECT * FROM application_repairs WHERE plan_id=?',(plan_id,)).fetchone()
                if record is None:raise PermissionError('Registered reviewed application flow required')
                return policy,dict(record)
        def prewrite(plan_id,original,content):
            policy,record=flow(plan_id)
            require_production_content(original.content);require_production_content(content)
            if not policy.permits(original.resource_type,original.resource_id) or (record['resource_type'],record['resource_id'])!=(original.resource_type,original.resource_id):raise PermissionError('Reviewed production target mismatch')
            if record['kind']=='repair':
                from wordpress_repair_diagnosis import diagnose_link
                import sqlite3
                with sqlite3.connect(workspace/'application.sqlite') as db:
                    scan=db.execute('SELECT created_at,report,inventory FROM application_scans WHERE scan_id=?',(record['scan_id'],)).fetchone()
                if scan is None or not 0<=instant()-scan[0]<900:raise PermissionError('Fresh diagnostic evidence required')
                report,inventory=json.loads(scan[1]),json.loads(scan[2])
                if not diagnose_link(report,record['broken_url'])['link_replacement_eligible']:raise PermissionError('Missing-destination evidence required')
                if not any((item['resource_type'],item['resource_id'],item['link'])==(record['resource_type'],record['resource_id'],record['source_url']) for item in inventory):raise PermissionError('Diagnostic resource binding required')
                if replace_broken_href(original.content,record['source_url'],record['broken_url'],record['replacement_url'])!=content:raise PermissionError('Only the exact diagnosed href change is admitted')
            elif record['kind']=='restore':
                parent=self.repair_record(session,site_id,record['parent_plan_id'])
                result=parent['result'] or {}
                if result.get('status')!='applied' or not result.get('verified_snapshot'):raise PermissionError('Verified parent repair required')
                verify_unchanged(original,ResourceSnapshot(**result['verified_snapshot']))
                if parent['payload']['original']['content']!=content:raise PermissionError('Restore differs from retained parent content')
            else:raise PermissionError('Unsupported production operation')
            return True
        def independent(plan_id,original,written,phase):
            policy,record=flow(plan_id)
            html=public_page(record['source_url'])
            verify_rendered_change(original,written,record['source_url'],policy.document['content_selector'],html)
            if phase=='apply' and record['kind']=='repair':
                flow(plan_id)
                verify_public_replacement(record['replacement_url'],row['origin'])
            flow(plan_id) # Observe policy/session revocation after public network I/O.
            return True
        engine.pre_write_validator=prewrite;engine.post_write_verifier=independent
        return engine,identity,row


class ProductionGuardApplication(GuardApplication):
    production_mode=True
    def __init__(self,sites,monitor,*,policy_provider,scope_policy=None,scanner=None,probe=None):
        self.policy_provider=policy_provider;policy=scope_policy if scope_policy is not None else policy_provider()
        super().__init__(sites,monitor,scanner=scanner,probe=probe)
        self.origins=frozenset((policy.origin,))
    def _admitted(self):
        policy=self.policy_provider()
        if policy.origin not in self.origins:raise PermissionError('Production admission origin changed')
        return policy
    def write_admission_active(self):
        try:self._admitted();return True
        except Exception:return False
    def proposals(self,*args,**kwargs):
        if not self.write_admission_active():return []
        policy=self._admitted()
        return [p for p in super().proposals(*args,**kwargs) if policy.permits(p['resource_type'],p['resource_id'])]
    def scan(self,*args,**kwargs):self._admitted();return super().scan(*args,**kwargs)
    def prepare_repair(self,*args,**kwargs):self._admitted();return super().prepare_repair(*args,**kwargs)
    def approve_and_apply(self,*args,**kwargs):self._admitted();return super().approve_and_apply(*args,**kwargs)
    def prepare_restore(self,*args,**kwargs):self._admitted();return super().prepare_restore(*args,**kwargs)


def configured_production_application():
    if os.environ.get('FG_AUTOFIX_PRODUCTION_AUTHORIZED')!='1':return None
    if os.environ.get('FG_GUARD_TEST_UI')=='1':raise ValueError('Test and production modes cannot be mixed')
    def policy_provider():
        if os.environ.get('FG_AUTOFIX_PRODUCTION_AUTHORIZED')!='1':raise PermissionError('Production admission revoked')
        return read_production_policy(os.environ['FG_AUTOFIX_PRODUCTION_POLICY_FILE'],os.environ['FG_AUTOFIX_VALIDATION_RECEIPT_FILE'],os.environ['FG_RELEASE_COMMIT'])
    # Expiry blocks network/mutations, not authenticated local recovery history.
    policy=read_production_policy(os.environ['FG_AUTOFIX_PRODUCTION_POLICY_FILE'],os.environ['FG_AUTOFIX_VALIDATION_RECEIPT_FILE'],os.environ['FG_RELEASE_COMMIT'],for_history=True)
    from runtime_state import require_existing_guard_state
    from operator_secrets import configured_master_keys
    from infrastructure_configuration import configured_external_store
    from customer_auth import CustomerAuth
    from monitoring_service import MonitoringService
    from guard_assets import GuardAssetDirectory
    require_existing_guard_state()
    keys=configured_master_keys();store=configured_external_store()
    if store is None:raise ValueError('Verified external backup configuration required')
    auth=CustomerAuth(os.environ['FG_CUSTOMER_AUTH_DB'])
    sites=ProductionCustomerSites(auth,os.environ['FG_CUSTOMER_DATA_ROOT'],keys,active_key_id=os.environ['FG_GUARD_KEY_ID'],object_store=store,
        gateway_factory=lambda origin,credentials:ProductionWordPressGateway(origin,credentials,policy_provider),policy_provider=policy_provider)
    monitor=MonitoringService(GuardAssetDirectory(sites),os.environ['FG_MONITOR_DB'])
    return ProductionGuardApplication(sites,monitor,policy_provider=policy_provider,scope_policy=policy)
