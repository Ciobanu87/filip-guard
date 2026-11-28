"""Unified authenticated customer flow. Mutations restricted to explicit .test labs.

Scanner/Advisor and monitoring remain read-only. The only offered proposal is an
exact broken-link replacement inside an authorized published post/page body.
No head/meta/plugin settings are silently treated as supported content repairs.
"""
from contextlib import contextmanager
from dataclasses import asdict
from html import escape,unescape
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sqlite3
import uuid
from urllib.parse import urljoin,urlsplit,urldefrag

from customer_auth import private_database,instant
from wordpress_execution_gate import _origin
from wordpress_revision_guard import ResourceSnapshot,verify_unchanged,RevisionMismatchError
from wordpress_secure_https import _https_request_exchange,parse_http_response
from monitoring_scan import SecureMonitoringScan,target_url
from link_resolver import suggest_replacements


class UnsupportedRepair(ValueError):pass


def canonical(url):
    host,path,_=target_url(urldefrag(url)[0])
    return 'https://'+host+path


def replace_broken_href(content,source_url,broken_url,replacement_url):
    """Change href value bytes only; preserve other markup/text/attributes exactly."""
    host=urlsplit(source_url).hostname
    target_url(broken_url,host);target_url(replacement_url,host)
    broken=canonical(broken_url)
    if broken==canonical(replacement_url):raise UnsupportedRepair('Replacement must differ')
    if re.search(r'<\s*(?:base|plaintext)\b',content,re.I):
        raise UnsupportedRepair('Unsupported document URL or raw-text context')
    offsets=[0]
    for match in re.finditer('\n',content):offsets.append(match.end())
    edits=[]
    class Anchors(HTMLParser):
        def __init__(self,**kwargs):
            super().__init__(**kwargs);self.blocked=[]
        inert={'textarea','title','xmp','iframe','noembed','noframes','template','noscript'}
        def handle_endtag(self,tag):
            if tag in self.blocked:
                index=len(self.blocked)-1-self.blocked[::-1].index(tag)
                del self.blocked[index:]
        def handle_starttag(self,tag,attrs):
            if tag in self.inert:
                self.blocked.append(tag);return
            if self.blocked or tag!='a':return
            hrefs=[v for k,v in attrs if k=='href']
            if len(hrefs)!=1 or hrefs[0] is None:return
            try:matches=canonical(urljoin(source_url,hrefs[0]))==broken
            except ValueError:return
            if not matches:return
            raw=self.get_starttag_text()
            found=list(re.finditer(r'''\bhref\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))''',raw,re.I))
            if len(found)!=1:raise UnsupportedRepair('Ambiguous anchor markup')
            match=found[0];group=next(index for index in (1,2,3) if match.group(index) is not None)
            if unescape(match.group(group))!=hrefs[0]:raise UnsupportedRepair('Ambiguous href source')
            line,column=self.getpos();base=offsets[line-1]+column
            edits.append((base+match.start(group),base+match.end(group),escape(replacement_url,quote=True)))
        handle_startendtag=handle_starttag
    parser=Anchors(convert_charrefs=True);parser.feed(content);parser.close()
    if not 1<=len(edits)<=20:raise UnsupportedRepair('The approved broken link is absent or too broadly repeated')
    result=content
    for start,end,value in reversed(edits):result=result[:start]+value+result[end:]
    return result


def verify_public_replacement(url,origin):
    host,path,_=target_url(url,urlsplit(origin).hostname)
    response=parse_http_response(_https_request_exchange(host,path,8,accept='text/html,application/xhtml+xml'))
    types=[value.split(';')[0].strip().lower() for key,value in response.headers if key.lower()=='content-type']
    if response.status!=200 or types not in (['text/html'],['application/xhtml+xml']) or not response.body.strip():
        raise UnsupportedRepair('Replacement must be a complete verified HTML page')
    return True


class GuardApplication:
    def __init__(self,sites,monitor,*,authorized_test_origins=(),scanner=None,probe=None,
                 simulated_storage=False,allow_registration=False):
        self.sites,self.auth,self.monitor=sites,sites.auth,monitor
        self.scanner=scanner if scanner is not None else SecureMonitoringScan()
        self.probe=probe if probe is not None else verify_public_replacement
        self.origins=frozenset('https://'+_origin(origin) for origin in authorized_test_origins)
        if any(not urlsplit(origin).hostname.endswith('.test') for origin in self.origins):
            raise ValueError('Only explicitly authorized isolated .test sites are supported in this UI')
        self.simulated_storage=bool(simulated_storage);self.allow_registration=bool(allow_registration)

    def _owned(self,session,site_id):
        principal,row=self.sites._owned(session,site_id)
        if row['origin'] not in self.origins:raise PermissionError('Site is outside the authorized test environment')
        return principal,row

    @contextmanager
    def db(self,session,site_id):
        principal,_=self._owned(session,site_id)
        root=self.sites._workspace(principal,site_id)
        path=private_database(root/'application.sqlite')
        db=sqlite3.connect(path,timeout=10);db.row_factory=sqlite3.Row
        try:
            with db:
                db.executescript('''CREATE TABLE IF NOT EXISTS application_scans (
                    scan_id TEXT PRIMARY KEY,created_at REAL NOT NULL,report TEXT NOT NULL,inventory TEXT NOT NULL);
                    CREATE TABLE IF NOT EXISTS application_repairs (
                    plan_id TEXT PRIMARY KEY,scan_id TEXT,kind TEXT NOT NULL,resource_id INTEGER NOT NULL,
                    resource_type TEXT NOT NULL,source_url TEXT NOT NULL,broken_url TEXT,replacement_url TEXT,
                    parent_plan_id TEXT,created_at REAL NOT NULL);
                ''')
                yield db
        finally:db.close()

    def connect(self,session,origin,username,password):
        origin='https://'+_origin(origin)
        if origin not in self.origins:raise PermissionError('Only an authorized isolated test site can be connected')
        return self.sites.connect(session,origin,username,password)

    def resources(self,session,site_id):
        self._owned(session,site_id)
        return self.sites.resources(session,site_id)

    def scan(self,session,site_id,*,start_url=None,page_limit=3):
        _,site=self._owned(session,site_id)
        target_url(start_url or site['origin'],urlsplit(site['origin']).hostname)
        def checkpoint():self._owned(session,site_id)
        report=self.scanner(site['origin'],page_limit=page_limit,max_requests=max(12,page_limit),
                            start_url=start_url,checkpoint=checkpoint)
        inventory=self.resources(session,site_id)
        scan_id=uuid.uuid4().hex
        with self.db(session,site_id) as db:
            db.execute('INSERT INTO application_scans VALUES (?, ?, ?, ?)',
                (scan_id,instant(),json.dumps(asdict(report)),json.dumps(inventory)))
        return self.scan_record(session,site_id,scan_id)

    def scan_record(self,session,site_id,scan_id=None):
        with self.db(session,site_id) as db:
            row=db.execute('SELECT * FROM application_scans '+('WHERE scan_id=?' if scan_id else 'ORDER BY created_at DESC LIMIT 1'),
                           (scan_id,) if scan_id else ()).fetchone()
        if row is None:
            if scan_id:raise PermissionError('Scan unavailable for this site')
            return None
        return {**dict(row),'report':json.loads(row['report']),'inventory':json.loads(row['inventory'])}

    def advice(self,session,site_id,scan_id=None,*,generate=False,advisor=None,language='en'):
        """Authenticated on-demand advice. Monitoring never calls inference.

        Model output is stored alongside its immutable scan, separately from the
        deterministic findings used to form supported AutoFix plans.
        """
        from contextual_advisor import configured_advisor,rule_result
        from advisor_language import render_language
        principal,_=self._owned(session,site_id)
        scan=self.scan_record(session,site_id,scan_id)
        if scan is None:return None
        contexts=dict(scan['report'].get('page_context',()))
        with self.db(session,site_id) as db:
            db.execute('CREATE TABLE IF NOT EXISTS application_advice (scan_id TEXT PRIMARY KEY,result TEXT NOT NULL)')
            old=db.execute('SELECT result FROM application_advice WHERE scan_id=?',(scan['scan_id'],)).fetchone()
        if not generate:return render_language(json.loads(old[0]) if old else rule_result(scan['report']['rows'],contexts),language)
        from advisor_ledger import AdvisorLedgerError
        result=None
        try:engine=advisor if advisor is not None else configured_advisor()
        except AdvisorLedgerError:
            engine=None;result=rule_result(scan['report']['rows'],contexts,status='usage-ledger-unavailable')
        except Exception:engine=None
        if engine is None:
            if result is None:result=rule_result(scan['report']['rows'],contexts,status='model-not-configured')
        else:
            try:
                result=engine.analyze(scan['report']['rows'],contexts,scope=principal.customer_id+':'+site_id,
                    checkpoint=lambda:self._owned(session,site_id))
            except AdvisorLedgerError:
                result=rule_result(scan['report']['rows'],contexts,status='usage-ledger-unavailable')
        self._owned(session,site_id)
        with self.db(session,site_id) as db:
            db.execute('INSERT OR REPLACE INTO application_advice VALUES (?,?)',(scan['scan_id'],json.dumps(result)))
        return render_language(result,language)

    def proposals(self,session,site_id,scan_id):
        scan=self.scan_record(session,site_id,scan_id);result=[]
        from wordpress_repair_diagnosis import diagnose_link
        for issue in scan['report']['findings']:
            if issue['scope_kind']!='link':continue
            diagnosis=diagnose_link(scan['report'],issue['scope_key'])
            if not diagnosis['link_replacement_eligible']:continue
            sources={canonical(source) for source in issue.get('sources',[])}
            for item in scan['inventory']:
                if canonical(item['link']) in sources:
                    candidates=suggest_replacements(issue['scope_key'],scan['inventory'])
                    result.append(dict(issue_key=issue['key'],broken_url=issue['scope_key'],source_url=item['link'],
                        resource_id=item['resource_id'],resource_type=item['resource_type'],candidates=candidates,diagnosis=diagnosis))
        return result

    def prepare_repair(self,session,site_id,scan_id,issue_key,resource_id,replacement_url):
        _,site=self._owned(session,site_id)
        scan=self.scan_record(session,site_id,scan_id)
        if not 0<=instant()-scan['created_at']<900:
            raise UnsupportedRepair('Scan evidence expired; prepare a new scan')
        proposal=next((p for p in self.proposals(session,site_id,scan_id)
                       if p['issue_key']==issue_key and p['resource_id']==resource_id),None)
        if proposal is None:raise UnsupportedRepair('No supported proposal for this scan/resource')
        target_url(replacement_url,urlsplit(site['origin']).hostname)
        if self.probe(replacement_url,site['origin']) is not True:
            raise UnsupportedRepair('Replacement URL could not be verified')
        original=self.sites.read_resource(session,site_id,proposal['resource_type'],resource_id)
        proposed=replace_broken_href(original.content,proposal['source_url'],proposal['broken_url'],replacement_url)
        review=self.sites.propose(session,site_id,proposal['resource_type'],resource_id,proposed)
        verify_unchanged(original,ResourceSnapshot(**review['original']))
        with self.db(session,site_id) as db:
            db.execute('INSERT INTO application_repairs VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, ?)',
                (review['plan_id'],scan_id,'repair',resource_id,proposal['resource_type'],proposal['source_url'],
                 proposal['broken_url'],replacement_url,instant()))
        return review

    def review(self,session,site_id,plan_id):
        self._flow(session,site_id,plan_id)
        return self.sites.review(session,site_id,plan_id)

    def _flow(self,session,site_id,plan_id):
        with self.db(session,site_id) as db:
            row=db.execute('SELECT * FROM application_repairs WHERE plan_id=?',(plan_id,)).fetchone()
        if row is None:raise PermissionError('Application repair unavailable for this site')
        return dict(row)

    def approve_and_apply(self,session,site_id,plan_id,*,confirmed=False):
        flow=self._flow(session,site_id,plan_id)
        if confirmed is not True:raise PermissionError('Explicit approval required')
        if flow['kind']=='repair':
            scan=self.scan_record(session,site_id,flow['scan_id'])
            if not 0<=instant()-scan['created_at']<900:
                raise UnsupportedRepair('Scan evidence expired; prepare a new scan')
            _,site=self._owned(session,site_id)
            if self.probe(flow['replacement_url'],site['origin']) is not True:
                raise UnsupportedRepair('Replacement is no longer verified reachable')
        token=self.sites.approve(session,site_id,plan_id,confirmed=True)
        return self.sites.apply(session,site_id,plan_id,token)

    def prepare_restore(self,session,site_id,plan_id):
        flow=self._flow(session,site_id,plan_id)
        record=self.sites.repair_record(session,site_id,plan_id)
        result=record['result'] or {}
        if result.get('status')!='applied' or not result.get('verified_snapshot'):
            raise PermissionError('Only an exactly verified applied repair can be restored automatically')
        expected=ResourceSnapshot(**result['verified_snapshot'])
        current=self.sites.read_resource(session,site_id,flow['resource_type'],flow['resource_id'])
        verify_unchanged(expected,current)
        original=self.sites.get_backup(session,site_id,result['backup_id'])
        review=self.sites.propose(session,site_id,flow['resource_type'],flow['resource_id'],original['content'])
        verify_unchanged(expected,ResourceSnapshot(**review['original']))
        with self.db(session,site_id) as db:
            db.execute('INSERT INTO application_repairs VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?)',
                (review['plan_id'],flow['scan_id'],'restore',flow['resource_id'],flow['resource_type'],flow['source_url'],plan_id,instant()))
        return review

    def history(self,session,site_id):
        with self.db(session,site_id) as db:
            rows=db.execute('SELECT * FROM application_repairs ORDER BY created_at DESC LIMIT 30').fetchall()
        return [{**dict(row),'repair':self.sites.repair_record(session,site_id,row['plan_id'])} for row in rows]

    def recovery_review(self,session,site_id,plan_id):
        """Read-only evidence after interruption; never clear a hold or grant retry.

        Matching proposed/original content does not prove operation ownership or
        verified restoration. A later editor can independently write those bytes.
        """
        flow=self._flow(session,site_id,plan_id)
        record=self.sites.repair_record(session,site_id,plan_id)
        result=record['result'] or {}
        if record['state'] not in ('preparing_backup','applying','outcome_unknown','rollback_unverified','rollback_conflict'):
            raise PermissionError('Only held operations require this recovery review')
        original=ResourceSnapshot(**record['payload']['original'])
        current=self.sites.read_resource(session,site_id,flow['resource_type'],flow['resource_id'])
        verify_unchanged(current,current)
        if (current.site_url,current.resource_type,current.resource_id)!=(original.site_url,original.resource_type,original.resource_id):
            raise PermissionError('Recovery resource identity mismatch')
        try:verify_unchanged(original,current);same_version=True
        except RevisionMismatchError:same_version=False
        observed='original' if current.content==original.content else 'proposed' if current.content==record['payload']['proposed_content'] else 'different'
        self._owned(session,site_id)
        return dict(plan_id=plan_id,recorded_status=record['state'],observed_content=observed,
            original_version_matches=same_version,backup_id=result.get('backup_id'),
            backup_revalidation_required=True,operation_outcome_proven=False,
            mutations_authorized=False,automatic_retry_allowed=False,requires_intervention=True)

    def renew_review(self,session,site_id,plan_id):
        flow=self._flow(session,site_id,plan_id)
        record=self.sites.repair_record(session,site_id,plan_id)
        if record['result'] and record['result'].get('status') not in ('conflict','rolled_back'):
            raise PermissionError('Completed or uncertain operations cannot be blindly retried')
        if flow['kind']=='restore':return self.prepare_restore(session,site_id,flow['parent_plan_id'])
        proposal=next((p for p in self.proposals(session,site_id,flow['scan_id'])
            if p['resource_id']==flow['resource_id'] and p['broken_url']==flow['broken_url']),None)
        if proposal is None:raise UnsupportedRepair('Prepare a new scan and proposal')
        return self.prepare_repair(session,site_id,flow['scan_id'],proposal['issue_key'],flow['resource_id'],flow['replacement_url'])
