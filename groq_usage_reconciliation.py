"""Operator recovery of owner-exported provider history, not lost cache reconstruction.

A single explicitly authorized synthetic key probe follows a verified import.
No credential is supplied by Actions. Existing budgets are never reduced.
"""
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sqlite3
import time

MODEL = 'qwen/qwen3.8-27b'
SOURCE_SHA = '4404ca2f0fa9c56482d012816a058d62c860bc553d30a018764a6820265bdaa8'
EXPORTED_AT = datetime(2026,11,27,8,19,3,tzinfo=timezone.utc).timestamp()
DAILY_CALLS = 20


def parse_export(raw):
    if not isinstance(raw, bytes) or len(raw)>1024*1024 or hashlib.sha256(raw).hexdigest()!=SOURCE_SHA:
        raise ValueError('Different owner export requires independent review')
    reader=csv.DictReader(io.StringIO(raw.decode('utf-8-sig')))
    required={'request_id','created_at','status_code','model','api_key_id','project_id',
              'input_tokens','input_non_cached_tokens','input_cached_tokens','input_audio_seconds','output_tokens'}
    if not required.issubset(reader.fieldnames or []):raise ValueError('Incomplete provider evidence')
    rows=[];seen=set();keys=set();projects=set();days={}
    for item in reader:
        identifier=item['request_id']
        if not re.fullmatch(r'req_[A-Za-z0-9]+',identifier) or identifier in seen:raise ValueError('Duplicate or invalid request')
        seen.add(identifier)
        stamp=int(item['created_at'])/1000
        if not EXPORTED_AT-7*86400<=stamp<=EXPORTED_AT:raise ValueError('Timestamp outside declared export window')
        status=int(item['status_code']);input_tokens=int(item['input_tokens']);output_tokens=int(item['output_tokens'])
        if status not in (200,429) or item['model']!=MODEL or min(input_tokens,output_tokens)<0:raise ValueError('Unreviewed evidence row')
        if int(item['input_cached_tokens'])+int(item['input_non_cached_tokens'])!=input_tokens or float(item['input_audio_seconds'])!=0:
            raise ValueError('Unreconciled token accounting')
        keys.add(item['api_key_id']);projects.add(item['project_id'])
        day=int(stamp//86400);totals=days.setdefault(day,{'requests':0,'input_tokens':0,'output_tokens':0})
        totals['requests']+=1;totals['input_tokens']+=input_tokens;totals['output_tokens']+=output_tokens
        rows.append((identifier,stamp,status,MODEL,item['api_key_id'],item['project_id'],input_tokens,output_tokens,SOURCE_SHA))
    if len(keys)!=1 or len(projects)!=1 or len(rows)!=15 or sum(x[2]==200 for x in rows)!=14:
        raise ValueError('Export scope/counts do not match reviewed evidence')
    if sum(x[6]+x[7] for x in rows)!=3898:raise ValueError('Reviewed token total mismatch')
    return rows,days


def import_history(db, raw, *, now):
    rows,days=parse_export(raw)
    db.execute('BEGIN IMMEDIATE')
    try:
        db.execute('CREATE TABLE IF NOT EXISTS advisor_requests (scope TEXT NOT NULL,request_hash TEXT NOT NULL,started REAL NOT NULL,expires REAL NOT NULL,day INTEGER NOT NULL,state TEXT NOT NULL,result TEXT,PRIMARY KEY(scope,request_hash))')
        db.execute('CREATE TABLE IF NOT EXISTS advisor_budget (day INTEGER PRIMARY KEY,calls INTEGER NOT NULL)')
        db.execute('CREATE TABLE IF NOT EXISTS recovered_provider_requests (request_id TEXT PRIMARY KEY,created_at REAL NOT NULL,http_status INTEGER NOT NULL,model TEXT NOT NULL,key_identifier TEXT NOT NULL,project_identifier TEXT NOT NULL,input_tokens INTEGER NOT NULL,output_tokens INTEGER NOT NULL,source_sha256 TEXT NOT NULL)')
        import advisor_quota
        advisor_quota.install(db)
        for row in rows:
            if row[2]==429:
                advisor_quota.record(db,'groq-free:'+MODEL,row[1]+20,{'code':'http_error','stage':'http','http_status':429,'quota_kind':'unknown'})
        db.execute('CREATE TABLE IF NOT EXISTS ai_recovery_policy (day INTEGER PRIMARY KEY,source_sha256 TEXT NOT NULL,provider_requests_exact INTEGER NOT NULL,local_reservations_recovered INTEGER NOT NULL,closed_day_budget_hold INTEGER NOT NULL)')
        for row in rows:
            previous=db.execute('SELECT * FROM recovered_provider_requests WHERE request_id=?',(row[0],)).fetchone()
            if previous is not None and tuple(previous)!=row:raise ValueError('Conflicting existing history')
            db.execute('INSERT OR IGNORE INTO recovered_provider_requests VALUES (?,?,?,?,?,?,?,?,?)',row)
        # These are explicitly labeled conservative HOLDS, not fabricated API
        # calls: local pre-network reservations in the lost SQLite are unknown.
        # Every elapsed day in the export window stays closed at the prior cap.
        first=int((EXPORTED_AT-7*86400)//86400);today=int(now//86400)
        for day in range(first,today+1):
            exact=days.get(day,{}).get('requests',0)
            hold=DAILY_CALLS if day<today else exact
            old_request_count=db.execute('SELECT count(*) FROM advisor_requests WHERE day=?',(day,)).fetchone()[0]
            db.execute('INSERT INTO advisor_budget VALUES (?,?) ON CONFLICT(day) DO UPDATE SET calls=MAX(calls,excluded.calls)',(day,max(hold,old_request_count)))
            db.execute('INSERT OR IGNORE INTO ai_recovery_policy VALUES (?,?,?,0,?)',(day,SOURCE_SHA,exact,int(day<today)))
        db.commit()
    except Exception:
        db.rollback();raise
    observed=db.execute('SELECT count(*),sum(input_tokens),sum(output_tokens) FROM recovered_provider_requests WHERE source_sha256=?',(SOURCE_SHA,)).fetchone()
    if tuple(observed)!=(15,3062,836):raise ValueError('Imported provider history not verified')
    if db.execute('PRAGMA quick_check').fetchone()!=('ok',):raise ValueError('Ledger integrity failure')
    return {'provider_requests_imported':15,'http_200':14,'http_429':1,'input_tokens':3062,'output_tokens':836,'total_tokens':3898,
            'scope':'owner-exported-Default-Project-seven-day-window','original_sqlite_recovered':False,
            'historical_local_reservations_unknown':True,'closed_historical_days_held_at_existing_call_cap':True,
            'quality_cache_reconstructed':False,'source_sha256':SOURCE_SHA,'reconciliation_verified':True}



def verified_daily_observation(raw):
    rows,days=parse_export(raw)
    return {'source_sha256':SOURCE_SHA,'exported_at_utc':EXPORTED_AT,'window_days':7,
            'scope':'Default Project; one exported API-key identifier; not other projects or organizations',
            'utc_day':'2026-11-24','requests':len(rows),'http_200':sum(row[2]==200 for row in rows),
            'http_429':sum(row[2]==429 for row in rows),'input_tokens':sum(row[6] for row in rows),
            'output_tokens':sum(row[7] for row in rows),'total_tokens':sum(row[6]+row[7] for row in rows),
            'per_request_original_retained_independently':True,'operator_verified_original_csv':True}


def import_verified_observation(db, observation, *, now):
    # The original CSV was verified offline against its pinned hash by the
    # operator. Only an aggregate already present in the reviewed public code
    # crosses Actions; no request/key/project IDs or per-request times do.
    expected={'source_sha256':SOURCE_SHA,'exported_at_utc':EXPORTED_AT,'window_days':7,
              'scope':'Default Project; one exported API-key identifier; not other projects or organizations',
              'utc_day':'2026-11-24','requests':15,'http_200':14,'http_429':1,
              'input_tokens':3062,'output_tokens':836,'total_tokens':3898,
              'per_request_original_retained_independently':True,'operator_verified_original_csv':True}
    if observation!=expected:raise ValueError('Different aggregate requires original-source verification')
    if int(now//86400)!=int(EXPORTED_AT//86400) or not 0<=now-EXPORTED_AT<=6*3600:
        raise ValueError('Stale observation cannot initialize current-day counters')
    source_day=int(datetime(2026,11,24,tzinfo=timezone.utc).timestamp()//86400)
    db.execute('BEGIN IMMEDIATE')
    try:
        db.execute('CREATE TABLE IF NOT EXISTS advisor_requests (scope TEXT NOT NULL,request_hash TEXT NOT NULL,started REAL NOT NULL,expires REAL NOT NULL,day INTEGER NOT NULL,state TEXT NOT NULL,result TEXT,PRIMARY KEY(scope,request_hash))')
        db.execute('CREATE TABLE IF NOT EXISTS advisor_budget (day INTEGER PRIMARY KEY,calls INTEGER NOT NULL)')
        db.execute('CREATE TABLE IF NOT EXISTS recovered_provider_daily (source_sha256 TEXT NOT NULL,day INTEGER NOT NULL,requests INTEGER NOT NULL,http_200 INTEGER NOT NULL,http_429 INTEGER NOT NULL,input_tokens INTEGER NOT NULL,output_tokens INTEGER NOT NULL,PRIMARY KEY(source_sha256,day))')
        row=(SOURCE_SHA,source_day,15,14,1,3062,836)
        old=db.execute('SELECT * FROM recovered_provider_daily WHERE source_sha256=? AND day=?',(SOURCE_SHA,source_day)).fetchone()
        if old is not None and tuple(old)!=row:raise ValueError('Conflicting existing recovery evidence')
        db.execute('INSERT OR IGNORE INTO recovered_provider_daily VALUES (?,?,?,?,?,?,?)',row)
        db.execute('CREATE TABLE IF NOT EXISTS ai_recovery_policy (day INTEGER PRIMARY KEY,source_sha256 TEXT NOT NULL,provider_requests_exact INTEGER NOT NULL,local_reservations_recovered INTEGER NOT NULL,closed_day_budget_hold INTEGER NOT NULL)')
        import advisor_quota
        advisor_quota.install(db)
        # Unknown historical cooldown: conservatively anchor the existing
        # 24-hour policy at the END of its observed UTC day, never shorten an
        # already retained deadline and never claim this is a provider reset.
        advisor_quota.record(db,'groq-free:'+MODEL,(source_day+1)*86400+20,
                             {'code':'http_error','stage':'http','http_status':429,'quota_kind':'unknown'})
        today=int(now//86400);first=int((EXPORTED_AT-7*86400)//86400)
        for day in range(first,today+1):
            exact=15 if day==source_day else 0
            hold=DAILY_CALLS if day<today else exact
            existing=db.execute('SELECT count(*) FROM advisor_requests WHERE day=?',(day,)).fetchone()[0]
            db.execute('INSERT INTO advisor_budget VALUES (?,?) ON CONFLICT(day) DO UPDATE SET calls=MAX(calls,excluded.calls)',(day,max(hold,existing)))
            db.execute('INSERT OR IGNORE INTO ai_recovery_policy VALUES (?,?,?,0,?)',(day,SOURCE_SHA,exact,int(day<today)))
        db.commit()
    except Exception:db.rollback();raise
    if tuple(db.execute('SELECT * FROM recovered_provider_daily WHERE source_sha256=? AND day=?',(SOURCE_SHA,source_day)).fetchone())!=row:
        raise ValueError('Imported aggregate mismatch')
    if db.execute('PRAGMA quick_check').fetchone()!=('ok',):raise ValueError('Reconciled ledger integrity failure')
    return {**observation,'provider_requests_accounted':15,'original_sqlite_recovered':False,
            'historical_local_reservations_unknown':True,'closed_historical_days_held_at_existing_call_cap':True,
            'quality_cache_reconstructed':False,'evidence_representation':'verified-daily-observation-with-original-retained-independently',
            'reconciliation_verified':True}

def retain(path, raw):
    if path.exists():
        if path.is_symlink() or path.read_bytes()!=raw:raise ValueError('Different retained recovery evidence')
        return
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as output:output.write(raw);output.flush();os.fsync(output.fileno())


def single_probe(db, recovery, key_path, *, now, exchange=None):
    """One durable attempt, even if an Action is rerun after a crash/timeout."""
    from advisor_groq import GroqFreeProvider
    from advisor_credentials import valid_groq_key
    from operator_secrets import private_file
    import advisor_quota
    from advisor_diagnostics import safe_diagnostic
    marker=recovery/'groq-oracle-key-validation-v1.attempt.json'
    receipt=recovery/'groq-oracle-key-validation-v1.receipt.json'
    if marker.exists():
        return {**json.loads(receipt.read_text()),'reused_receipt':True,'new_provider_attempts':0} if receipt.is_file() else {'status':'previous-attempt-held-no-retry','new_provider_attempts':0}
    if int(now//86400)!=int(EXPORTED_AT//86400) or not 0<=now-EXPORTED_AT<=6*3600:
        raise ValueError('Export must cover the current UTC day and remain fresh')
    provider_name='groq-free:'+MODEL
    advisor_quota.install(db)
    advisor_quota.migrate_legacy(db,provider_name)
    db.commit()
    if advisor_quota.active(db,provider_name,now):raise ValueError('Existing provider cooldown remains in force')
    if db.execute("SELECT 1 FROM advisor_requests WHERE state='pending' AND expires>?",(now,)).fetchone():
        raise ValueError('Another reservation remains pending')
    latest=db.execute('SELECT MAX(started) FROM advisor_requests').fetchone()[0]
    if latest is not None and now-latest<61:raise ValueError('Existing minute admission remains in force')
    # Format/readability only, entirely inside app-user memory; no HTTP.
    candidate=valid_groq_key(private_file(key_path,256).decode('ascii').strip())
    provider=GroqFreeProvider(lambda:candidate,free_plan_confirmed=True,data_consent=True)
    day=int(now//86400);scope='0'*32+':'+'1'*32
    digest=hashlib.sha256(b'oracle-key-probe-v1:'+SOURCE_SHA.encode()).hexdigest()
    db.execute('BEGIN IMMEDIATE')
    try:
        if db.execute('UPDATE advisor_budget SET calls=calls+1 WHERE day=? AND calls<?',(day,DAILY_CALLS)).rowcount!=1:
            raise ValueError('Existing daily admission denied')
        fd=os.open(marker,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'w') as output:
            json.dump({'scope':'single-owner-authorized-synthetic-key-check','started':now,'source_sha256':SOURCE_SHA},output)
            output.flush();os.fsync(output.fileno())
        db.execute('INSERT INTO advisor_requests VALUES (?,?,?,?,?,?,NULL)',(scope,digest,now,now+30,day,'pending'))
        db.commit()
    except Exception:
        db.rollback();raise
    directory=os.open(recovery,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(directory)
    finally:os.close(directory)
    messages=[{'role':'system','content':'Synthetic connection check. Return only the required JSON object.'},
              {'role':'user','content':'Return {"status":"ok"}. No tools, browsing, customer data or actions.'}]
    schema={'type':'object','properties':{'status':{'type':'string','enum':['ok']}},'required':['status'],'additionalProperties':False}
    result={'status':'controlled-key-validation-failed','new_provider_attempts':1,'automatic_retries':0,'services_started':False}
    try:
        if exchange is not None:
            payload=exchange(provider,messages,schema)
        else:payload=provider.generate(messages,schema,timeout=15,max_output_tokens=64)
        if payload!={'status':'ok'}:raise ValueError('Synthetic response contract rejected')
        result.update(status='controlled-key-validation-accepted',model=MODEL,usage=provider.last_usage,quota=provider.last_quota)
    except Exception as error:
        result['diagnostic']=safe_diagnostic(error)
        if advisor_quota.is_quota(result['diagnostic']):advisor_quota.record(db,provider_name,time.time(),result['diagnostic'])
    finally:
        result['new_provider_attempts']=provider.attempted_exchanges
        candidate=None;provider.keys=lambda:None
        db.execute('UPDATE advisor_requests SET state=?,result=? WHERE scope=? AND request_hash=?',
                   ('complete' if result['status']=='controlled-key-validation-accepted' else 'failed',json.dumps(result),scope,digest));db.commit()
        retain(receipt,json.dumps(result,sort_keys=True).encode())
    return result


def run_host(data):
    os.umask(0o077)
    if os.geteuid()==0:raise ValueError('Application uid required')
    observation=data['verified_observation']
    now=time.time()
    if int(now//86400)!=int(EXPORTED_AT//86400) or not 0<=now-EXPORTED_AT<=6*3600:
        raise ValueError('Stale export cannot initialize current-day counters')
    evidence=data['historical_evidence']
    if evidence.get('accepted_case_count')!=9 or evidence.get('all_nine_fixture_results_preserved') is not True:
        raise ValueError('Historical quality evidence missing')
    state=Path('/srv/filip-guard/state');recovery=Path('/srv/filip-guard/recovery')
    if (state/'FG-RESTORE-REVIEW-REQUIRED').exists():raise ValueError('Independent restore hold remains')
    for folder in (state,recovery):
        if folder.is_symlink() or folder.stat().st_mode&0o077:raise ValueError('Private persistent directories required')
    path=state/'advisor.sqlite'
    if path.is_symlink():raise ValueError('Unsafe ledger path')
    if path.exists():
        if not path.is_file() or path.stat().st_nlink!=1:raise ValueError('Regular unlinked ledger required')
        if path.stat().st_mode&0o077:raise ValueError('Unsafe existing ledger')
        # Keep an exact existing-state snapshot before adding recovery evidence.
        original=sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True)
        try:
            original.execute('SELECT scope,request_hash,started,expires,day,state,result FROM advisor_requests LIMIT 0')
            original.execute('SELECT day,calls FROM advisor_budget LIMIT 0')
            backup_path=recovery/'advisor-before-groq-reconciliation.sqlite'
            if not backup_path.exists():
                snapshot=sqlite3.connect(backup_path)
                try:original.backup(snapshot)
                finally:snapshot.close()
                backup_path.chmod(0o600)
        finally:original.close()
    retain(recovery/'groq-provider-observation-20261127.json',json.dumps(observation,sort_keys=True).encode())
    retain(recovery/'groq-nine-accepted-historical-evidence.json',json.dumps(evidence,sort_keys=True).encode())
    # Publish a newly reconstructed ledger only after its history and counters
    # are verified. A failed import never leaves an empty production database.
    if not path.exists():
        import tempfile
        fd,staged=tempfile.mkstemp(prefix='.advisor-reconciliation-',dir=state);os.close(fd)
        staged=Path(staged)
        try:
            temporary_db=sqlite3.connect(staged)
            try:
                temporary_db.execute('PRAGMA synchronous=FULL')
                import_verified_observation(temporary_db,observation,now=time.time())
            finally:temporary_db.close()
            os.link(staged,path)  # atomic publication, refusing any concurrent target
            directory=os.open(state,os.O_RDONLY|os.O_DIRECTORY)
            try:os.fsync(directory)
            finally:os.close(directory)
        finally:staged.unlink(missing_ok=True)
    db=sqlite3.connect(path,timeout=10);path.chmod(0o600)
    try:
        db.execute('PRAGMA synchronous=FULL')
        report=import_verified_observation(db,observation,now=time.time())
        retain(recovery/'groq-provider-reconciliation-v1.json',json.dumps(report,sort_keys=True).encode())
        if data.get('one_synthetic_probe_authorized') is not True:raise ValueError('Single probe authorization missing')
        probe=single_probe(db,recovery,Path('/etc/filip-guard/secrets/groq-api-key'),now=time.time())
        return {'status':'provider-history-reconciled','history':report,'probe':probe,'ai_services_enabled':False}
    finally:db.close()
