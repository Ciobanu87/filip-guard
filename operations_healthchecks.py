"""One authorized operator tick. Does not activate app, AI, backup or repairs."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import stat
import subprocess
import time
from operations_alerting import Incidents,emit,opaque,endpoint
from operations_observer import collect

UNITS=('filip-guard-ui.service','filip-guard-worker.service','filip-guard-state-backup.service')


def private_json(path):
    path=Path(path);info=path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or info.st_uid!=0 or info.st_mode&0o077 or info.st_size>8192:raise ValueError('Root-controlled private configuration required')
    return json.loads(path.read_text())


def service_state(unit):
    if unit not in (*UNITS,'systemd-journald.service'):raise ValueError('Unknown unit')
    result=subprocess.run(['systemctl','show',unit,'--property=LoadState,ActiveState,Result,InvocationID','--no-pager'],capture_output=True,text=True,timeout=5,check=True)
    return dict(line.split('=',1) for line in result.stdout.splitlines() if '=' in line)


@__import__('contextlib').contextmanager
def restart_interlock(path='/run/filip-guard-backup.lock'):
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    try:
        info=os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid!=0 or info.st_nlink!=1 or info.st_mode&0o077:raise ValueError('Trusted backup interlock required')
        fcntl.flock(fd,fcntl.LOCK_SH|fcntl.LOCK_NB)
        yield
    finally:os.close(fd)


def recover_worker(journal,*,now,properties,gate,runner=subprocess.run):
    # Never start a stopped service; never restart UI or replay customer writes.
    if properties.get('ActiveState')!='active' or not gate():return 'held'
    if not any(kind=='worker' for _,kind,_ in journal.active()):return 'unnecessary'
    if not journal.reserve_restart('filip-guard-worker.service',now):return 'limit-reached'
    runner(['systemctl','try-restart','filip-guard-worker.service'],capture_output=True,timeout=15,check=True)
    # A successful systemctl command is NOT recovery proof. Heartbeat must advance.
    return 'requested-not-yet-verified'


def main(argv=None):
    parser=argparse.ArgumentParser();parser.add_argument('--config',default='/etc/filip-guard/healthchecks.json');parser.add_argument('--once',action='store_true',required=True)
    args=parser.parse_args(argv)
    try:
        config=private_json(args.config)
        required={'schema','authorized','host_url','incident_url','expected_ui','expected_worker','expected_ai','expected_backup','recover_worker'}
        if set(config)!=required or config['schema']!=1 or config['authorized'] is not True:raise ValueError('Explicit operator authorization required')
        for key in ('expected_ui','expected_worker','expected_ai','expected_backup','recover_worker'):
            if type(config[key]) is not bool:raise ValueError('Explicit expected-state flags required')
        endpoint(config['host_url']);endpoint(config['incident_url'])
        if config['host_url']==config['incident_url']:raise ValueError('Independent host and incident checks required')
        root=Path('/srv/filip-guard/operations');journal=Incidents(root)
        fd=os.open(root/'observer.lock',os.O_WRONLY|os.O_CREAT|os.O_NOFOLLOW,0o600)
        try:
            fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            now=time.time()
            if service_state('systemd-journald.service').get('ActiveState')!='active':raise ValueError('Active journal required')
            properties={unit:service_state(unit) for unit in UNITS}
            for unit,item in properties.items():
                expected=config['expected_worker'] if unit.endswith('worker.service') else config['expected_backup'] if 'backup' in unit else config['expected_ui']
                if expected and (item.get('LoadState')!='loaded' or item.get('Result') not in ('success','',None)):
                    journal.fail('service',opaque('service',unit),now)
            if properties[UNITS[2]].get('ActiveState')!='active':
                for unit,expected in ((UNITS[0],config['expected_ui']),(UNITS[1],config['expected_worker'])):
                    if expected and properties[unit].get('ActiveState')!='active':journal.fail('service',opaque('service',unit),now)
            from operations_journal import collect_journal
            collect_journal(journal)
            backup=properties[UNITS[2]]
            collect('/srv/filip-guard/state',journal,now=now,expect_ai=config['expected_ai'],expect_worker=config['expected_worker'] and backup.get('ActiveState')!='active',backup_failed=backup.get('InvocationID','unknown') if config['expected_backup'] and backup.get('Result') not in ('success','',None) else None)
            if config['expected_ui'] and backup.get('ActiveState')!='active':
                from operations_observer import ui_health
                if properties[UNITS[0]].get('ActiveState')=='active':ui_health(journal,now=now)
            if config['expected_backup']:
                from operations_observer import backup_freshness
                backup_freshness('/srv/filip-guard/recovery',journal,now=now)
            if config['recover_worker'] and backup.get('ActiveState')!='active':
                def gate():
                    try:
                        import sys
                        sys.path.insert(0,'/opt/filip-guard')
                        from operations_host_gate import host_gate
                        host_gate({'FG_CUSTOMER_AUTH_DB':'/srv/filip-guard/state/accounts.sqlite','FG_CUSTOMER_DATA_ROOT':'/srv/filip-guard/state/sites','FG_MONITOR_DB':'/srv/filip-guard/state/monitor.sqlite','FG_AI_LEDGER_DB':'/srv/filip-guard/state/advisor.sqlite'});return True
                    except Exception:return False
                if any(kind=='worker' for _,kind,_ in journal.active()):
                    with restart_interlock():
                        recover_worker(journal,now=now,properties=properties[UNITS[1]],gate=gate)
            summary=emit(journal,config['host_url'],config['incident_url'])
        finally:os.close(fd)
        print(json.dumps({'status':'observer-completed',**summary}));return 0 if summary['heartbeat_confirmed'] else 1
    except Exception:
        # The external dead-man detects absent heartbeat if collector/config hangs.
        print('{"status":"observer-held-or-failed","secrets_logged":false}');return 1


if __name__=='__main__':raise SystemExit(main())
