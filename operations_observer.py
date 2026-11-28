"""Bounded, read-only adapters for existing private application evidence."""
from pathlib import Path
import sqlite3
from operations_alerting import opaque


def read_db(path,query,args=()):
    path=Path(path)
    # Missing DBs never get created, symlinked sources never get followed.
    if path.is_symlink() or not path.is_file():raise ValueError('Existing evidence required')
    db=sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True,timeout=2)
    try:
        db.execute('PRAGMA query_only=ON')
        db.set_progress_handler(lambda:1 if __import__('time').monotonic()>deadline else 0,1000)
        deadline=__import__('time').monotonic()+2
        return db.execute(query,args).fetchall()
    finally:db.close()


def collect(state,journal,*,now,expect_ai=False,expect_worker=False,backup_failed=None):
    root=Path(state)
    if root.is_symlink() or not root.is_dir():raise ValueError('Existing state root required')
    files=list(__import__('itertools').islice(root.glob('sites/*/*/repairs.sqlite'),1001))
    if len(files)>1000:raise ValueError('Bounded source inventory exceeded')
    for path in files:
        if any(p.is_symlink() for p in (path.parent,path.parent.parent,root/'sites')):raise ValueError('Unsafe evidence hierarchy')
        rows=read_db(path,'SELECT plan_id,state,expires_at FROM repair_plans LIMIT 10001')
        if len(rows)>10000:raise ValueError('Bounded repair inventory exceeded')
        for plan,status,expires in rows:
            kind=None
            if status in ('rollback_unverified','rollback_conflict'):kind='rollback'
            elif status=='outcome_unknown':kind='autofix'
            elif status in ('preparing_backup','applying') and now>expires+600:kind='autofix'
            if kind:journal.fail(kind,opaque('repair',str(path.relative_to(root)),plan,status),min(now,expires))
            # No automatic resolution/replay of a repair, including uncertain results.
    if expect_ai:
        rows=read_db(root/'advisor.sqlite',"SELECT state,max(started) FROM advisor_requests WHERE state IN ('failed','readiness-failure','transient','complete','pending') GROUP BY state")
        times=dict(rows);failed=max((times.get(k,0) for k in ('failed','readiness-failure','transient')),default=0)
        success=times.get('complete',0)
        source=opaque('provider','groq')
        if failed>success:journal.fail('ai',source,failed)
        # A cooldown expiring is not proof of provider recovery; only an actual
        # already-authorized successful request can confirm an AI recovery.
        if success>failed:
            active={item[0] for item in journal.active()}
            if source in active:journal.confirm(source,opaque('verified-ai-success',success),success)
        if times.get('pending',now)>0:
            stale=read_db(root/'advisor.sqlite',"SELECT min(expires) FROM advisor_requests WHERE state='pending'")[0][0]
            if stale is not None and now>stale+600:journal.fail('ai',opaque('ai-stalled'),stale)
    if expect_worker:
        rows=read_db(root/'monitor.sqlite',"SELECT value FROM monitor_runtime WHERE name='heartbeat'")
        if not rows or now>rows[0][0]+600:journal.fail('worker',opaque('worker-stalled'),now if not rows else rows[0][0]+600)
        else:
            source=opaque('worker-stalled')
            prior=[x for x in journal.active() if x[0]==source]
            if prior and rows[0][0]>prior[0][2]:journal.confirm(source,opaque('fresh-worker-heartbeat',rows[0][0]),now)
    if backup_failed:journal.fail('backup',opaque('backup',backup_failed),now)
    return {'sources_read':len(files),'active_incidents':len(journal.active())}


def backup_freshness(directory,journal,*,now):
    """Local existing readback receipt only. No B2 probe/upload/retry."""
    import json
    import re
    root=Path(directory)
    if root.is_symlink() or not root.is_dir():raise ValueError('Existing recovery evidence required')
    paths=list(__import__('itertools').islice(root.glob('*.json'),10001))
    if len(paths)>10000:raise ValueError('Bounded receipt inventory exceeded')
    newest=0
    required={'scope','deployment_id','key_id','object_id','ciphertext_sha256'}
    for path in paths:
        if path.is_symlink() or path.stat().st_size>8192:raise ValueError('Unsafe receipt')
        data=json.loads(path.read_text())
        if type(data) is dict and set(data)==required and data['scope']=='application_sqlite_state' and re.fullmatch('[0-9a-f]{64}',str(data['ciphertext_sha256'])):
            at=path.stat().st_mtime
            if at>now+60:raise ValueError('Future backup evidence')
            newest=max(newest,at)
    if not newest or now-newest>26*3600:
        journal.fail('backup',opaque('backup-stale'),now if not newest else newest+26*3600)
    # No passive auto-clear: a manifest is not a new independent readback proof.


def ui_health(journal,*,now,connection_factory=None):
    """Read only the fixed private Streamlit health route, never a customer page."""
    import http.client
    connection=(connection_factory or http.client.HTTPConnection)('127.0.0.1',8501,timeout=2)
    source=opaque('ui-health')
    try:
        connection.request('GET','/_stcore/health',headers={'Connection':'close'})
        response=connection.getresponse()
        healthy=response.status==200 and response.read(33).strip()==b'ok'
    except (OSError,http.client.HTTPException):healthy=False
    finally:connection.close()
    if not healthy:journal.fail('service',source,now)
    else:
        active={x[0]:x for x in journal.active()}
        for identity in (source,opaque('service','filip-guard-ui.service')):
            if identity in active and now>active[identity][2]:journal.confirm(identity,opaque('verified-loopback-health',now),now)
