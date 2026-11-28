"""Approved controls for the independent observer only. No app activation."""
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import time

BASE=Path('/opt/filip-guard-operations')
APP=('filip-guard-ui.service','filip-guard-worker.service','filip-guard-state-backup.service','filip-guard-state-backup.timer')
MONITOR='filip-guard-operator-monitor.service'
TIMER='filip-guard-operator-monitor.timer'


def command(args):return subprocess.run(args,capture_output=True,text=True,timeout=65)


def app_states():return [command(['systemctl','is-active',name]).stdout.strip() for name in APP]


def run(data):
    if os.geteuid()!=0:raise ValueError('Root operator controller required')
    if set(data)!={'action','hashes','free_plan_confirmed','email_channel_confirmed','external_down_seen'}:raise ValueError('Fixed request required')
    action=data['action']
    if action not in ('inspect','activate','synthetic-failure','synthetic-recovery'):raise ValueError('Unapproved control')
    before=app_states()
    if any(s!='inactive' for s in before):raise ValueError('Application remains held for this phase')
    expected={'operations_alerting.py','operations_observer.py','operations_healthchecks.py','operations_journal.py','operations_confirm_recovery.py','operations_healthchecks_entry.py'}
    if set(data['hashes'])!=expected or BASE.is_symlink():raise ValueError('Reviewed installed observer required')
    for name,digest in data['hashes'].items():
        path=BASE/name;info=path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid!=0 or info.st_mode&0o022 or hashlib.sha256(path.read_bytes()).hexdigest()!=digest:raise ValueError('Installed observer differs')
    sys.path.insert(0,str(BASE))
    from operations_healthchecks import private_json
    from operations_alerting import endpoint,Incidents,opaque
    config_path=Path('/etc/filip-guard/healthchecks.json')
    present=config_path.exists()
    report=dict(status='operator-inspected',config_present=present,action=action,production_active=False,groq_calls=0,b2_calls=0)
    if action!='inspect':
        if data['free_plan_confirmed'] is not True or data['email_channel_confirmed'] is not True:raise ValueError('Free account and verified email evidence required')
        if not present:return {**report,'status':'operator-held-missing-private-config','guard_unit_states_unchanged':app_states()==before}
        config=private_json(config_path)
        if config.get('authorized') is not True or any(config.get(k) is not False for k in ('expected_ui','expected_worker','expected_ai','expected_backup','recover_worker')):raise ValueError('Application expected-state flags must stay held')
        endpoint(config['host_url']);endpoint(config['incident_url'])
        if config['host_url']==config['incident_url']:raise ValueError('Separate ingestion endpoints required')
        if action=='activate':
            if command(['systemctl','start',MONITOR]).returncode:raise ValueError('Initial observer tick did not succeed')
            if command(['systemctl','enable','--now',TIMER]).returncode:raise ValueError('Observer timer did not start')
        else:
            journal=Incidents('/srv/filip-guard/operations');source=opaque('healthchecks-integration-test-v1')
            if action=='synthetic-failure':journal.fail('observer',source,time.time())
            else:
                if data['external_down_seen'] is not True:raise ValueError('External failure observation required before synthetic recovery')
                if source not in {r[0] for r in journal.active()}:raise ValueError('Existing synthetic incident required')
                journal.confirm(source,opaque('verified-external-synthetic-failure'),time.time())
            if command(['systemctl','start',MONITOR]).returncode:raise ValueError('Observer delivery needs review')
        report['status']='operator-action-completed'
    report['operator_timer_active']=command(['systemctl','is-active',TIMER]).stdout.strip()=='active'
    report['guard_unit_states_unchanged']=app_states()==before
    if not report['guard_unit_states_unchanged']:raise ValueError('Application unit state changed unexpectedly')
    return report


if __name__=='__main__':
    try:
        raw=sys.stdin.buffer.read(8193)
        if len(raw)>8192:raise ValueError('Request size exceeded')
        report=run(json.loads(raw))
    except Exception:report={'status':'operator-control-held-or-failed','production_active':False}
    print(json.dumps(report,sort_keys=True))
