"""Install owner-interactive helper or retrieve ONLY an encrypted custody bundle."""
import base64
import hashlib
import json
import os
from pathlib import Path
import shlex
import sys
from operations_oracle_bootstrap import validate_authorization
from operations_oracle_ssh_probe import run_pinned_command

ROOT=Path(__file__).parent
INSTALL=r'''
import hashlib,json,os,stat,subprocess,sys,tempfile
from pathlib import Path
config=Path('/etc/filip-guard');data=json.loads(sys.stdin.buffer.read(65537))
if json.loads((config/'host-install-receipt.json').read_text())['evidence_sha256']!=data['evidence_sha256']:raise ValueError('Wrong verified host')
if json.loads((config/'ssh-recovery/pending.json').read_text())['status']!='confirmed':raise ValueError('SSH hardening not confirmed')
for unit in ('filip-guard-ui.service','filip-guard-worker.service','filip-guard-state-backup.service','filip-guard-state-backup.timer'):
    result=subprocess.run(['/usr/bin/systemctl','is-active',unit],capture_output=True,text=True,timeout=10)
    if result.stdout.strip()!='inactive':raise ValueError('No service may run')
source=data['source'].encode()
if len(source)>32768 or hashlib.sha256(source).hexdigest()!=data['source_sha256']:raise ValueError('Different reviewed helper')
compile(source,'owner-interactive-master-custody','exec')
path=Path('/usr/local/sbin/filip-guard-master-custody')
if path.exists() or path.is_symlink():
    info=path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid!=0 or stat.S_IMODE(info.st_mode)!=0o700 or path.read_bytes()!=source:raise ValueError('Different installed helper is never overwritten')
else:
    fd,temporary=tempfile.mkstemp(prefix='.fg-owner-custody-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as output:
            output.write(source);output.flush();os.fsync(output.fileno());os.fchmod(output.fileno(),0o700)
        os.replace(temporary,path)
    finally:
        if os.path.exists(temporary):os.unlink(temporary)
print(json.dumps({'status':'owner-interactive-master-custody-helper-prepared','master_key_generated':False,
                  'master_key_exported':False,'groq_api_calls':0,'b2_api_calls':0,'services_started':False}))
'''


def authorization(data):
    expected={'generation_requires_owner_interactive_secret':True,'encrypted_github_artifact_only':True,
              'artifact_retention_days':1,'plaintext_master_export_authorized':False,
              'plaintext_master_library_storage_authorized':False,'service_activation_authorized':False,
              'groq_calls_authorized':0,'b2_calls_before_free_caps_verification_authorized':0}
    if any(type(data.get(k)) is not type(v) or data.get(k)!=v for k,v in expected.items()):raise ValueError('Exact existing owner custody scope required')


def main():
    if sys.argv[1:] not in (['install-helper'],['export-sealed'],['status']):raise ValueError('Explicit owner custody operation required')
    authorization(json.loads((ROOT/'deployment/oracle-owner-custody-request.json').read_text()))
    evidence=(ROOT/'deployment/oracle-prepared/owner-evidence-20261126.json').read_bytes()
    approved=validate_authorization(json.loads((ROOT/'deployment/oracle-host-setup-request.json').read_text()),evidence,os.environ)
    if sys.argv[1]=='install-helper':
        source=(ROOT/'owner_master_custody.py').read_text()
        data={'source':source,'source_sha256':hashlib.sha256(source.encode()).hexdigest(),'evidence_sha256':approved['evidence_sha256']}
        result=json.loads(run_pinned_command('sudo -n -- /opt/filip-guard/.venv/bin/python -c '+shlex.quote(INSTALL),operation='host-setup',input_data=json.dumps(data).encode(),timeout=60))
        if result.get('status')!='owner-interactive-master-custody-helper-prepared':raise ValueError('Installation unverified')
    elif sys.argv[1]=='status':
        result=json.loads(run_pinned_command('sudo -n -- /usr/local/sbin/filip-guard-master-custody status',operation='host-setup',timeout=60))
        expected={'status','master_installed_private','runtime_binding_matches','independent_owner_custody_verified','groq_api_calls','b2_api_calls','services_started'}
        if set(result)!=expected or result.get('status')!='owner-custody-status-verified':raise ValueError('Custody status not available')
        if any(result.get(name) is not True for name in ('master_installed_private','runtime_binding_matches','independent_owner_custody_verified')):raise ValueError('Independent owner custody still pending')
        if result.get('services_started') is not False or result.get('groq_api_calls')!=0 or result.get('b2_api_calls')!=0:raise ValueError('Read-only custody scope required')
    else:
        result=json.loads(run_pinned_command('sudo -n -- /usr/local/sbin/filip-guard-master-custody export-sealed',operation='host-setup',timeout=60))
        if result.get('status')=='encrypted-owner-custody-export':
            bundle=result['bundle']
            if set(bundle)!={'format','envelope','application_state_check'} or set(bundle['envelope'])!={'format','key_id','deployment_id','kdf','iterations','salt','nonce','ciphertext'}:
                raise ValueError('Unexpected private material is never exported')
            if len(base64.b64decode(bundle['envelope']['ciphertext'],validate=True))!=48:raise ValueError('Encrypted master format required')
            encoded=json.dumps(bundle,sort_keys=True,separators=(',',':')).encode('ascii')
            if len(encoded)>3800:raise ValueError('Bounded encrypted owner bundle required')
            path=Path(os.environ['RUNNER_TEMP'])/'filip-guard-master-custody-v1.sealed.json'
            fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(fd,'wb') as output:output.write(encoded)
            with open(os.environ['GITHUB_OUTPUT'],'a') as output:output.write('bundle_ready=true\n')
            result={'status':'encrypted-custody-artifact-ready','artifact_retention_days':1,
                    'owner_offline_recovery_still_required':True,'plaintext_master_exported':False,'services_started':False}
        elif result.get('status')!='awaiting-owner-interactive-custody-preparation':raise ValueError('Unreviewed custody export')
    print(json.dumps(result,sort_keys=True))


if __name__=='__main__':
    try:main()
    except Exception:
        print('{"status":"owner-custody-operation-held-or-failed","services_started":false,"plaintext_master_exported":false}')
        raise SystemExit(1)
