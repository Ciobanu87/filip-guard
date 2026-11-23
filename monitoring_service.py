"""Durable authorized-site scheduling, fenced workers, history and in-app alerts.

Background consent is independent of browser-session lifetime. Workers check the
current account/site binding before requests and cannot invoke AutoFix or email.
"""
from contextlib import contextmanager
from dataclasses import asdict
import json
import secrets
import sqlite3
import time
import uuid
from urllib.parse import urlsplit

from customer_auth import private_database,instant
from monitoring_scan import SecureMonitoringScan,MonitoringReport,MonitoringCancelled,target_url


class LeaseLost(MonitoringCancelled): pass


def _json(value):return json.dumps(value,separators=(',',':'),ensure_ascii=True,allow_nan=False)


class MonitoringService:
    MIN_INTERVAL=900
    MAX_ATTEMPTS=3
    def __init__(self,directory,database_path,*,scanner=None,lease_seconds=90,notification_window=3600):
        if type(lease_seconds) is not int or not 90<=lease_seconds<=300:raise ValueError('Invalid monitoring lease')
        if type(notification_window) is not int or not 900<=notification_window<=86400:raise ValueError('Invalid notification window')
        self.directory,self.auth=directory,directory.auth
        self.path=private_database(database_path)
        self.scanner=scanner if scanner is not None else SecureMonitoringScan()
        self.lease_seconds,self.window=lease_seconds,notification_window
        with self.db() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS monitor_schedules (
                site_id TEXT PRIMARY KEY, customer_id TEXT NOT NULL, origin TEXT NOT NULL,
                enabled INTEGER NOT NULL, interval_seconds INTEGER NOT NULL,
                page_limit INTEGER NOT NULL, max_requests INTEGER NOT NULL, next_due REAL NOT NULL,
                revision INTEGER NOT NULL, lease_token TEXT, lease_until REAL, run_id TEXT,
                last_request REAL, last_error INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS monitor_runs (
                run_id TEXT PRIMARY KEY, site_id TEXT NOT NULL, customer_id TEXT NOT NULL,
                scheduled_at REAL NOT NULL, started_at REAL NOT NULL, finished_at REAL,
                attempts INTEGER NOT NULL, state TEXT NOT NULL, requests INTEGER NOT NULL DEFAULT 0,
                report TEXT, error TEXT, UNIQUE(site_id,scheduled_at));
                CREATE TABLE IF NOT EXISTS monitor_findings (
                customer_id TEXT NOT NULL, site_id TEXT NOT NULL, finding_key TEXT NOT NULL,
                payload TEXT NOT NULL, first_seen REAL NOT NULL, last_seen REAL NOT NULL, resolved_at REAL,
                PRIMARY KEY(customer_id,site_id,finding_key));
                CREATE TABLE IF NOT EXISTS monitor_notifications (
                notification_id TEXT PRIMARY KEY, customer_id TEXT NOT NULL, site_id TEXT NOT NULL,
                bucket INTEGER NOT NULL, kind TEXT NOT NULL, payload TEXT NOT NULL,
                event_count INTEGER NOT NULL, created_at REAL NOT NULL, updated_at REAL NOT NULL, read_at REAL,
                UNIQUE(customer_id,site_id,bucket,kind));
                CREATE TABLE IF NOT EXISTS monitor_email_outbox (
                notification_id TEXT PRIMARY KEY, state TEXT NOT NULL, not_before REAL NOT NULL,
                lease_token TEXT, lease_until REAL, attempts INTEGER NOT NULL DEFAULT 0,
                sent_at REAL, error TEXT);
                CREATE INDEX IF NOT EXISTS monitor_due ON monitor_schedules(enabled,next_due);
            ''')

    @contextmanager
    def db(self):
        db=sqlite3.connect(self.path,timeout=10);db.row_factory=sqlite3.Row
        try:
            with db:yield db
        finally:db.close()

    def _owned(self,session,site_id,now=None):return self.directory._owned(session,site_id,now=now)

    def configure(self,session,site_id,*,enabled,interval_seconds=3600,page_limit=5,max_requests=20,now=None):
        principal,site=self._owned(session,site_id,now);timestamp=instant(now)
        if (type(enabled) is not bool or type(interval_seconds) is not int
                or not self.MIN_INTERVAL<=interval_seconds<=604800
                or type(page_limit) is not int or not 1<=page_limit<=30
                or type(max_requests) is not int or not page_limit<=max_requests<=60):
            raise ValueError('Invalid monitoring configuration')
        target_url(site['origin'])
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT * FROM monitor_schedules WHERE site_id=?',(site_id,)).fetchone()
            if row and row['customer_id']!=principal.customer_id:raise PermissionError('Monitoring site ownership mismatch')
            values=(int(enabled),interval_seconds,page_limit,max_requests)
            if row and values==tuple(row[key] for key in ('enabled','interval_seconds','page_limit','max_requests')):
                return self.snapshot(session,site_id,now=now)
            latest=db.execute('SELECT MAX(scheduled_at) FROM monitor_runs WHERE site_id=?',(site_id,)).fetchone()[0]
            due=max(timestamp,latest+self.MIN_INTERVAL) if latest is not None else timestamp
            if row:
                if row['run_id']:
                    db.execute("UPDATE monitor_runs SET state='cancelled',finished_at=? WHERE run_id=? AND state='running'",
                               (timestamp,row['run_id']))
                db.execute('''UPDATE monitor_schedules SET enabled=?,interval_seconds=?,page_limit=?,max_requests=?,
                    next_due=?,revision=revision+1,lease_token=NULL,lease_until=NULL,run_id=NULL WHERE site_id=?''',
                    (*values,due,site_id))
            else:
                db.execute('''INSERT INTO monitor_schedules
                    (site_id,customer_id,origin,enabled,interval_seconds,page_limit,max_requests,next_due,revision)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)''',
                    (site_id,principal.customer_id,site['origin'],*values,due))
        return self.snapshot(session,site_id,now=now)

    def snapshot(self,session,site_id,*,now=None):
        principal,_=self._owned(session,site_id,now)
        with self.db() as db:
            schedule=db.execute('''SELECT enabled,interval_seconds,page_limit,max_requests,next_due
                FROM monitor_schedules WHERE customer_id=? AND site_id=?''',(principal.customer_id,site_id)).fetchone()
            last=db.execute('''SELECT run_id,scheduled_at,started_at,finished_at,state,requests,error FROM monitor_runs
                WHERE customer_id=? AND site_id=? ORDER BY scheduled_at DESC LIMIT 1''',(principal.customer_id,site_id)).fetchone()
            findings=db.execute('''SELECT payload FROM monitor_findings WHERE customer_id=? AND site_id=?
                AND resolved_at IS NULL ORDER BY finding_key LIMIT 200''',(principal.customer_id,site_id)).fetchall()
        return dict(schedule=dict(schedule) if schedule else None,last_check=dict(last) if last else None,
                    findings=[json.loads(row[0]) for row in findings],repairs_authorized=False)

    def history(self,session,site_id,*,limit=20,now=None):
        principal,_=self._owned(session,site_id,now)
        if type(limit) is not int or not 1<=limit<=100:raise ValueError('Invalid history bound')
        with self.db() as db:
            rows=db.execute('''SELECT run_id,scheduled_at,started_at,finished_at,state,requests,error,report
                FROM monitor_runs WHERE customer_id=? AND site_id=? ORDER BY scheduled_at DESC LIMIT ?''',
                (principal.customer_id,site_id,limit)).fetchall()
        return [{**dict(row),'report':json.loads(row['report']) if row['report'] else None} for row in rows]

    def notifications(self,session,*,limit=50,now=None):
        principal=self.auth.resolve(session,now=now)
        if type(limit) is not int or not 1<=limit<=100:raise ValueError('Invalid notification bound')
        with self.db() as db:
            rows=db.execute('''SELECT notification_id,site_id,kind,payload,event_count,created_at,updated_at,read_at
                FROM monitor_notifications WHERE customer_id=? ORDER BY updated_at DESC LIMIT ?''',
                (principal.customer_id,limit)).fetchall()
        return [{**dict(row),'payload':json.loads(row['payload'])} for row in rows]

    def mark_read(self,session,notification_id,*,now=None):
        principal=self.auth.resolve(session,now=now)
        with self.db() as db:
            changed=db.execute('UPDATE monitor_notifications SET read_at=? WHERE notification_id=? AND customer_id=?',
                               (instant(now),notification_id,principal.customer_id))
            if changed.rowcount!=1:raise PermissionError('Notification unavailable for this account')

    def _binding(self,customer_id,site_id,origin):
        with self.directory.db() as db:
            site=db.execute('SELECT 1 FROM customer_sites WHERE customer_id=? AND site_id=? AND origin=?',
                            (customer_id,site_id,origin)).fetchone()
        with self.auth.db() as db:
            active=db.execute('SELECT 1 FROM customers WHERE customer_id=? AND active=1',(customer_id,)).fetchone()
        return bool(site and active)

    def _notify(self,db,job,kind,payload,timestamp):
        bucket=int(timestamp//self.window)
        row=db.execute('''SELECT * FROM monitor_notifications WHERE customer_id=? AND site_id=? AND bucket=? AND kind=?''',
                       (job['customer_id'],job['site_id'],bucket,kind)).fetchone()
        if row:
            events=json.loads(row['payload'])['events'];events.append(payload)
            db.execute('''UPDATE monitor_notifications SET payload=?,event_count=event_count+1,
                updated_at=?,read_at=NULL WHERE notification_id=?''',
                (_json(dict(origin=job['origin'],events=events[-20:])),timestamp,row['notification_id']))
        else:
            identifier=uuid.uuid4().hex
            db.execute('INSERT INTO monitor_notifications VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, NULL)',
                (identifier,job['customer_id'],job['site_id'],bucket,kind,
                 _json(dict(origin=job['origin'],events=[payload])),timestamp,timestamp))
            db.execute("INSERT INTO monitor_email_outbox(notification_id,state,not_before) VALUES (?, 'pending', ?)",
                       (identifier,(bucket+1)*self.window))

    def _valid_job(self,db,job,timestamp):
        row=db.execute('SELECT * FROM monitor_schedules WHERE site_id=?',(job['site_id'],)).fetchone()
        if (row is None or not row['enabled'] or row['customer_id']!=job['customer_id']
                or row['lease_token']!=job['lease_token'] or row['run_id']!=job['run_id']
                or not timestamp<row['lease_until']):raise LeaseLost('Monitoring lease lost')
        return row

    def claim(self,*,now=None):
        timestamp=instant(now)
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            rows=db.execute('''SELECT * FROM monitor_schedules WHERE enabled=1 AND next_due<=?
                AND (lease_token IS NULL OR lease_until<=?) ORDER BY next_due,site_id LIMIT 100''',
                (timestamp,timestamp)).fetchall()
            for row in rows:
                job=dict(row)
                if not self._binding(row['customer_id'],row['site_id'],row['origin']):
                    db.execute('UPDATE monitor_schedules SET enabled=0,lease_token=NULL,lease_until=NULL WHERE site_id=?',(row['site_id'],))
                    continue
                previous=db.execute('SELECT * FROM monitor_runs WHERE run_id=?',(row['run_id'],)).fetchone() if row['run_id'] else None
                if previous and (previous['attempts']>=self.MAX_ATTEMPTS or previous['requests']>=row['max_requests']):
                    db.execute("UPDATE monitor_runs SET state='error',finished_at=?,error='Recovery budget exhausted' WHERE run_id=?",
                               (timestamp,row['run_id']))
                    if not row['last_error']:self._notify(db,job,'monitoring_error',dict(message='Monitoring recovery budget exhausted'),timestamp)
                    db.execute('''UPDATE monitor_schedules SET last_error=1,next_due=?,lease_token=NULL,
                        lease_until=NULL,run_id=NULL WHERE site_id=?''',(timestamp+row['interval_seconds'],row['site_id']))
                    continue
                run_id=previous['run_id'] if previous else uuid.uuid4().hex
                if previous:
                    db.execute('UPDATE monitor_runs SET attempts=attempts+1,started_at=? WHERE run_id=?',(timestamp,run_id))
                else:
                    db.execute('''INSERT INTO monitor_runs(run_id,site_id,customer_id,scheduled_at,started_at,attempts,state)
                        VALUES (?, ?, ?, ?, ?, 1, 'running')''',
                        (run_id,row['site_id'],row['customer_id'],row['next_due'],timestamp))
                token=secrets.token_urlsafe(32)
                db.execute('UPDATE monitor_schedules SET lease_token=?,lease_until=?,run_id=? WHERE site_id=?',
                           (token,timestamp+self.lease_seconds,run_id,row['site_id']))
                return {**job,'lease_token':token,'lease_until':timestamp+self.lease_seconds,'run_id':run_id}
        return None

    def checkpoint(self,job,*,now=None):
        with self.db() as db:self._valid_job(db,job,instant(now))
        if not self._binding(job['customer_id'],job['site_id'],job['origin']):
            raise MonitoringCancelled('Site monitoring authorization revoked')

    def reserve_request(self,job,*,now=None,min_gap=1):
        timestamp=instant(now)
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE');schedule=self._valid_job(db,job,timestamp)
            run=db.execute('SELECT requests FROM monitor_runs WHERE run_id=?',(job['run_id'],)).fetchone()
            if run['requests']>=schedule['max_requests']:raise ValueError('Durable monitoring request budget exhausted')
            wait=max(0,(schedule['last_request']+min_gap-timestamp)) if schedule['last_request'] is not None else 0
            if wait:return wait
            db.execute('UPDATE monitor_runs SET requests=requests+1 WHERE run_id=?',(job['run_id'],))
            db.execute('UPDATE monitor_schedules SET last_request=? WHERE site_id=?',(timestamp,job['site_id']))
        return 0

    def publish(self,job,report=None,*,error=None,now=None):
        timestamp=instant(now)
        if report is not None:
            if type(report) is not MonitoringReport or len(report.rows)>30 or len(report.findings)>200:
                raise ValueError('Invalid monitoring report')
            host=urlsplit(job['origin']).hostname
            for row in report.rows:target_url(row['page'],host)
            for finding in report.findings:
                target_url(finding['scope_key'],host)
                if finding.get('autofix') is not False:raise ValueError('Monitoring cannot authorize repairs')
            serialized=_json(asdict(report))
            if len(serialized)>2_000_000:raise ValueError('Monitoring result too large')
        else:serialized=None
        if not self._binding(job['customer_id'],job['site_id'],job['origin']):raise MonitoringCancelled('Monitoring authorization revoked')
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE');schedule=self._valid_job(db,job,timestamp)
            new=[];resolved=[];changed=[]
            if report is not None:
                old_rows=db.execute('SELECT * FROM monitor_findings WHERE customer_id=? AND site_id=?',
                                    (job['customer_id'],job['site_id'])).fetchall()
                old={row['finding_key']:row for row in old_rows};current={finding['key']:finding for finding in report.findings}
                for key,payload in current.items():
                    if key not in old or old[key]['resolved_at'] is not None:new.append(payload)
                    db.execute('''INSERT INTO monitor_findings VALUES (?, ?, ?, ?, ?, ?, NULL)
                        ON CONFLICT(customer_id,site_id,finding_key) DO UPDATE SET payload=excluded.payload,
                        last_seen=excluded.last_seen,resolved_at=NULL''',
                        (job['customer_id'],job['site_id'],key,_json(payload),timestamp,timestamp))
                scope={tuple(item) for item in report.scope}
                for key,row in old.items():
                    payload=json.loads(row['payload'])
                    covered=(payload['scope_kind'],payload['scope_key']) in scope
                    sources=payload.get('sources',[])
                    removed=(payload['scope_kind']=='link' and bool(sources)
                        and all(('source',source) in scope for source in sources)
                        and payload['scope_key'] not in report.discovered_links)
                    if key not in current and row['resolved_at'] is None and (covered or removed):
                        resolved.append(payload)
                        db.execute('UPDATE monitor_findings SET resolved_at=? WHERE customer_id=? AND site_id=? AND finding_key=?',
                                   (timestamp,job['customer_id'],job['site_id'],key))
                previous=db.execute('''SELECT report FROM monitor_runs WHERE site_id=? AND customer_id=?
                    AND report IS NOT NULL AND run_id!=? ORDER BY scheduled_at DESC LIMIT 1''',
                    (job['site_id'],job['customer_id'],job['run_id'])).fetchone()
                if previous:
                    baseline={row['page']:row for row in json.loads(previous['report'])['rows']}
                    for row in report.rows:
                        oldrow=baseline.get(row['page'])
                        if oldrow and type(row['http_status']) is int and type(oldrow['http_status']) is int:
                            fields=[name for name in ('http_status','title','meta_description','h1_count','images_missing_alt')
                                    if row.get(name)!=oldrow.get(name)]
                            if fields:changed.append(dict(page=row['page'],fields=fields))
                if new or resolved or changed:
                    self._notify(db,job,'changes',dict(new_count=len(new),resolved_count=len(resolved),changed_count=len(changed),
                        new=new[:10],resolved=resolved[:10],changed=changed[:10]),timestamp)
            incomplete=error is not None or report is None or not report.complete
            if incomplete and not schedule['last_error']:
                self._notify(db,job,'monitoring_error',dict(message='Monitoring check incomplete; unverified issues were not resolved.'),timestamp)
            elif not incomplete and schedule['last_error']:
                self._notify(db,job,'monitoring_recovered',dict(message='Monitoring checks recovered.'),timestamp)
            state='error' if report is None else 'partial' if incomplete else 'complete'
            db.execute('UPDATE monitor_runs SET state=?,finished_at=?,report=?,error=? WHERE run_id=?',
                       (state,timestamp,serialized,'Monitoring check incomplete' if incomplete else None,job['run_id']))
            db.execute('''UPDATE monitor_schedules SET next_due=?,lease_token=NULL,lease_until=NULL,run_id=NULL,last_error=?
                WHERE site_id=?''',(timestamp+schedule['interval_seconds'],int(incomplete),job['site_id']))
            db.execute('''DELETE FROM monitor_runs WHERE site_id=? AND run_id IN
                (SELECT run_id FROM monitor_runs WHERE site_id=? ORDER BY scheduled_at DESC LIMIT -1 OFFSET 1000)''',
                (job['site_id'],job['site_id']))
        return dict(run_id=job['run_id'],status=state,new=len(new),resolved=len(resolved),changed=len(changed),repairs_authorized=False)

    def cancel(self,job,*,now=None):
        timestamp=instant(now)
        with self.db() as db:
            row=db.execute('SELECT lease_token FROM monitor_schedules WHERE site_id=?',(job['site_id'],)).fetchone()
            if row and row['lease_token']==job['lease_token']:
                db.execute("UPDATE monitor_runs SET state='cancelled',finished_at=? WHERE run_id=?",(timestamp,job['run_id']))
                db.execute('UPDATE monitor_schedules SET enabled=0,lease_token=NULL,lease_until=NULL,run_id=NULL WHERE site_id=?',(job['site_id'],))

    def run_once(self,*,now=None):
        job=self.claim(now=now)
        if job is None:return {'status':'idle','repairs_authorized':False}
        def checkpoint():self.checkpoint(job,now=now)
        def reserve():
            while True:
                checkpoint();wait=self.reserve_request(job,now=now)
                if not wait:return
                if now is not None:raise ValueError('Test clock must advance to the request slot')
                time.sleep(min(wait,1))
        try:
            checkpoint()
            report=self.scanner(job['origin'],page_limit=job['page_limit'],max_requests=job['max_requests'],
                                before_request=reserve,checkpoint=checkpoint)
            return self.publish(job,report,now=now)
        except LeaseLost:
            return {'status':'superseded','repairs_authorized':False}
        except MonitoringCancelled:
            self.cancel(job,now=now)
            return {'status':'cancelled','repairs_authorized':False}
        except Exception:
            try:return self.publish(job,error='Monitoring failed',now=now)
            except MonitoringCancelled:return {'status':'superseded','repairs_authorized':False}
