"""Install only a root-owned interactive helper; no Groq key is supplied."""
import hashlib
import json
import os
from pathlib import Path
import shlex
from operations_oracle_bootstrap import validate_authorization
from operations_oracle_ssh_probe import run_pinned_command

ROOT=Path(__file__).parent
REMOTE=r'''
import hashlib,json,os,stat,subprocess,sys,tempfile
from pathlib import Path
config=Path('/etc/filip-guard')
data=json.loads(sys.stdin.buffer.read(65537))
source=data['source'].encode()
if len(source)>32768 or hashlib.sha256(source).hexdigest()!=data['sha256']:raise ValueError('Unexpected helper payload')
if json.loads((config/'host-install-receipt.json').read_text())['evidence_sha256']!=data['evidence_sha256']:raise ValueError('Wrong host')
if json.loads((config/'ssh-recovery/pending.json').read_text())['status']!='confirmed':raise ValueError('SSH not confirmed')
for unit in ('filip-guard-ui.service','filip-guard-worker.service','filip-guard-state-backup.timer'):
    result=subprocess.run(['/usr/bin/systemctl','is-active',unit],capture_output=True,text=True,timeout=10)
    if result.stdout.strip()!='inactive':raise ValueError('Services must remain held')
if (config/'secrets/groq-api-key').exists():raise ValueError('Credential already present; review separately')
compile(source,'owner-interactive-groq-entry','exec')
path=Path('/usr/local/sbin/filip-guard-set-groq-key')
if path.exists() or path.is_symlink():
    info=path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid!=0 or info.st_mode&0o077 or path.read_bytes()!=source:
        raise ValueError('Different installed helper is never overwritten')
else:
    fd,temporary=tempfile.mkstemp(prefix='.fg-owner-entry-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as output:
            output.write(source);output.flush();os.fsync(output.fileno());os.fchmod(output.fileno(),0o700)
        os.replace(temporary,path)
    finally:
        if os.path.exists(temporary):os.unlink(temporary)
info=path.lstat()
if info.st_uid!=0 or stat.S_IMODE(info.st_mode)!=0o700 or hashlib.sha256(path.read_bytes()).hexdigest()!=data['sha256']:
    raise ValueError('Helper installation not verified')
print(json.dumps({'status':'owner-interactive-groq-entry-prepared','helper_root_owned':True,'helper_mode':'0700',
 'groq_key_supplied':False,'groq_api_calls':0,'services_started':False,'runtime_configuration_changed':False}))
'''


def main():
    evidence=(ROOT/'deployment/oracle-prepared/owner-evidence-20261126.json').read_bytes()
    approved=validate_authorization(json.loads((ROOT/'deployment/oracle-host-setup-request.json').read_text()),evidence,os.environ)
    source=(ROOT/'deployment/oracle_groq_key_entry.py').read_text()
    payload={'source':source,'sha256':hashlib.sha256(source.encode()).hexdigest(),'evidence_sha256':approved['evidence_sha256']}
    result=json.loads(run_pinned_command('sudo -n -- /usr/bin/python3 -c '+shlex.quote(REMOTE),
                       operation='host-setup',input_data=json.dumps(payload).encode(),timeout=60))
    if result.get('status')!='owner-interactive-groq-entry-prepared':raise ValueError('Installation unverified')
    print(json.dumps(result,sort_keys=True))


if __name__=='__main__':
    try:main()
    except Exception:
        print('{"status":"owner-key-entry-preparation-failed","groq_api_calls":0}');raise SystemExit(1)
