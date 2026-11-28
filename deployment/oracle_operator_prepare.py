"""Install independent held operator code/units, never start or change the app."""
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile

FILES={'operations_alerting.py','operations_observer.py','operations_healthchecks.py','operations_journal.py','operations_confirm_recovery.py','operations_healthchecks_entry.py'}
UNITS=('filip-guard-ui.service','filip-guard-worker.service','filip-guard-state-backup.service','filip-guard-state-backup.timer')
BASE=Path('/opt/filip-guard-operations')


def states():
    return [subprocess.run(['systemctl','is-active',u],capture_output=True,text=True,timeout=3).stdout.strip() for u in UNITS]


def directory(path):
    if any(p.is_symlink() for p in (path,*path.parents)):raise ValueError('Unsafe directory hierarchy')
    path.mkdir(mode=0o700,parents=False,exist_ok=True)
    if path.stat().st_uid!=0 or path.stat().st_mode&0o077:raise ValueError('Root private directory required')


def write_once_or_same(path,content,mode):
    if path.exists() or path.is_symlink():
        info=path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid!=0 or info.st_nlink!=1 or info.st_mode&0o022 or path.read_bytes()!=content:raise ValueError('Existing file differs; no overwrite')
        return
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,mode)
    with os.fdopen(fd,'wb') as output:output.write(content);output.flush();os.fsync(output.fileno())


def run(data):
    if os.geteuid()!=0:raise ValueError('Root installer required')
    before=states()
    if any(s!='inactive' for s in before):raise ValueError('Application must remain inactive')
    if set(data)!={'files','units'} or set(data['files'])!=FILES:raise ValueError('Fixed operator payload required')
    expected={'filip-guard-operator-monitor.service','filip-guard-operator-monitor.timer'}
    if set(data['units'])!=expected:raise ValueError('Only separate operator units allowed')
    if (Path('/etc/filip-guard')/'healthchecks.json').exists():raise ValueError('Live configuration already exists; review first')
    # Read-only repeat of allocation, no paid API or package installation.
    import urllib.request
    request=urllib.request.Request('http://169.254.169.254/opc/v2/instance/',headers={'Authorization':'Bearer Oracle'})
    with urllib.request.urlopen(request,timeout=2) as response:meta=json.loads(response.read(65536))
    shape=meta.get('shapeConfig',{})
    if meta.get('shape')!='VM.Standard.A1.Flex' or shape.get('ocpus')!=1 or shape.get('memoryInGBs')!=6:raise ValueError('Reviewed existing allocation required')
    directory(BASE);directory(Path('/srv/filip-guard/operations'));directory(Path('/srv/filip-guard/operations/reviewed-recovery'))
    for name,text in data['files'].items():
        compile(text,name,'exec');write_once_or_same(BASE/name,text.encode(),0o600)
    for name,text in data['units'].items():
        if name.endswith('.service') and ('ExecStart=/usr/bin/python3 /opt/filip-guard-operations/operations_healthchecks.py --once' not in text or 'ProtectSystem=strict' not in text):raise ValueError('Unexpected unit')
        write_once_or_same(Path('/etc/systemd/system')/name,text.encode(),0o644)
    # Runtime lock is the same shared/exclusive interlock used by daily backups.
    path=Path('/run/filip-guard-backup.lock')
    if not path.exists():write_once_or_same(path,b'',0o600)
    subprocess.run(['systemd-analyze','verify',*[str(Path('/etc/systemd/system')/n) for n in expected]],capture_output=True,check=True,timeout=15)
    subprocess.run(['systemctl','daemon-reload'],capture_output=True,check=True,timeout=10)
    timer=subprocess.run(['systemctl','is-enabled','filip-guard-operator-monitor.timer'],capture_output=True,text=True,timeout=5).stdout.strip()
    active=subprocess.run(['systemctl','is-active','filip-guard-operator-monitor.timer'],capture_output=True,text=True,timeout=5).stdout.strip()
    if timer!='disabled' or active!='inactive' or states()!=before:raise ValueError('Held state not confirmed')
    # Dependency-free operator probe on a disposable private journal, no network.
    sys.path.insert(0,str(BASE))
    from operations_alerting import Incidents,opaque,emit
    with tempfile.TemporaryDirectory(prefix='fg-observer-proof-') as temp:
        journal=Incidents(temp);source=opaque('synthetic-uncertain')
        journal.fail('autofix',source,1)
        seen=[];emit(journal,'host','incident',send=lambda u,f:seen.append((u,f)) or True)
        if seen!=[('incident',True),('host',False)] or len(Incidents(temp).active())!=1:raise ValueError('Incident latch failed')
        journal.confirm(source,opaque('synthetic-confirmed-recovery'),2)
        if journal.active():raise ValueError('Recovery confirmation failed')
    return dict(status='operator-prepared-held',operator_timer_active=False,production_active=False,
                guard_unit_states_unchanged=True,synthetic_latch_recovery_verified=True,live_email_verified=False,
                external_ping_requests=0,packages_installed=0,groq_calls=0,b2_calls=0)


if __name__=='__main__':
    try:
        raw=sys.stdin.buffer.read(128*1024+1)
        if len(raw)>128*1024:raise ValueError('Bounded operator payload required')
        result=run(json.loads(raw))
    except Exception:result={'status':'operator-preparation-held-or-failed','production_active':False}
    print(json.dumps(result))
