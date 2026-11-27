"""Encrypted owner-export transfer and gated single Groq check on the existing host."""
import json
import os
from pathlib import Path
import shlex
import sys
from operations_oracle_bootstrap import validate_authorization
from operations_oracle_ssh_probe import run_pinned_command

ROOT=Path(__file__).parent
REMOTE=r'''
import base64,hashlib,json,os,pwd,stat,subprocess,sys,tempfile
from pathlib import Path
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import rsa,padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
config=Path('/etc/filip-guard');transport=config/'groq-recovery-transfer.pem'
data=json.loads(sys.stdin.buffer.read(2*1024*1024+1))
if json.loads((config/'host-install-receipt.json').read_text())['evidence_sha256']!=data['evidence_sha256']:raise ValueError('Wrong approved host')
if json.loads((config/'ssh-recovery/pending.json').read_text())['status']!='confirmed':raise ValueError('SSH not confirmed')
authorization=data['authorization']
if (authorization['maximum_new_provider_attempts']!=1 or authorization['automatic_retries']!=0
    or authorization['paid_services_authorized'] is not False or authorization['application_master_key_operations'] is not False
    or authorization['systemd_service_activation'] is not False or authorization['free_plan_owner_confirmed'] is not True):
    raise ValueError('Current one-call-only authorization missing')
settings=dict(line.split('=',1) for line in (config/'runtime.env').read_text().splitlines() if line and not line.startswith('#') and '=' in line)
if settings.get('FG_AI_AUTHORIZED')!='0' or settings.get('FG_STATE_BACKUP_AUTHORIZED')!='0':raise ValueError('Services must remain held')
for unit in ('filip-guard-ui.service','filip-guard-worker.service','filip-guard-state-backup.timer'):
    result=subprocess.run(['/usr/bin/systemctl','is-active',unit],capture_output=True,text=True,timeout=10)
    if result.stdout.strip()!='inactive':raise ValueError('Unexpected active service')
if data['mode']=='prepare':
    if transport.exists() or transport.is_symlink():
        info=transport.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid!=0 or stat.S_IMODE(info.st_mode)!=0o600:raise ValueError('Unsafe transfer key')
        private=serialization.load_pem_private_key(transport.read_bytes(),password=None)
    else:
        private=rsa.generate_private_key(public_exponent=65537,key_size=3072)
        fd=os.open(transport,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'wb') as out:
            out.write(private.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()));out.flush();os.fsync(out.fileno())
    public=private.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    print(json.dumps({'status':'private-recovery-transfer-prepared','public_key_pem':public,'groq_calls':0,'master_key_operations':0,'services_started':False}))
elif data['mode']=='reconcile-and-probe':
    info=transport.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid!=0 or stat.S_IMODE(info.st_mode)!=0o600:raise ValueError('Unsafe transfer key')
    private=serialization.load_pem_private_key(transport.read_bytes(),password=None)
    sealed=data['sealed']
    if sealed['schema']!='fg-owner-provider-export-aes256gcm-rsa3072-v1':raise ValueError('Unreviewed encrypted input')
    key=private.decrypt(base64.b64decode(sealed['wrapped_key'],validate=True),padding.OAEP(mgf=padding.MGF1(hashes.SHA256()),algorithm=hashes.SHA256(),label=b'fg-groq-reconciliation-v1'))
    raw=AESGCM(key).decrypt(base64.b64decode(sealed['nonce'],validate=True),base64.b64decode(sealed['ciphertext'],validate=True),b'fg-groq-reconciliation-v1')
    payload=json.loads(raw)
    if payload.get('one_synthetic_probe_authorized') is not True:raise ValueError('No single probe authorization')
    user=pwd.getpwnam('filipguard')
    # Source is public operator code; all private evidence goes only to stdin.
    source=data['source']+'\nif __name__ == "__main__":\n import sys\n print(json.dumps(run_host(json.load(sys.stdin)),sort_keys=True))\n'
    env=['PATH=/usr/bin:/bin','PYTHONPATH=/opt/filip-guard','PYTHONDONTWRITEBYTECODE=1',
         'HOME=/var/cache/filip-guard','FG_AI_AUTHORIZED=0','FG_EMAIL_AUTHORIZED=0','FG_STATE_BACKUP_AUTHORIZED=0']
    result=subprocess.run(['/usr/sbin/runuser','-u','filipguard','--','/usr/bin/env','-i',*env,
                           '/opt/filip-guard/.venv/bin/python','-c',source],input=json.dumps(payload),capture_output=True,text=True,timeout=90)
    if result.returncode or len(result.stdout)>3500:
        print(json.dumps({'status':'reconciliation-or-single-probe-unverified','automatic_retries':0,'services_started':False}));raise SystemExit(1)
    report=json.loads(result.stdout)
    print(json.dumps(report,sort_keys=True))
else:raise ValueError('Unreviewed recovery operation')
'''


def validate_probe_authorization(data):
    expected={'scope':'owner-export-reconciliation-then-one-synthetic-groq-key-check',
              'authorized_on':'2026-11-27','prerequisite':'verified-provider-history-import-with-no-existing-counter-reduction',
              'source_sha256':'4404ca2f0fa9c56482d012816a058d62c860bc553d30a018764a6820265bdaa8',
              'maximum_new_provider_attempts':1,'automatic_retries':0,'model':'qwen/qwen3.8-27b','maximum_output_tokens':64,
              'free_plan_owner_confirmed':True,'paid_services_authorized':False,'systemd_service_activation':False,
              'application_master_key_operations':False,'new_cloud_resources':False,'repeat_nine_accepted_cases':False}
    if any(type(data.get(k)) is not type(v) or data.get(k)!=v for k,v in expected.items()):
        raise ValueError('Current owner one-call scope required separately from historical host-only approval')


def main():
    if sys.argv[1:] not in (['prepare'],['reconcile-and-probe']):raise ValueError('Explicit operator mode required')
    evidence=(ROOT/'deployment/oracle-prepared/owner-evidence-20261126.json').read_bytes()
    approved=validate_authorization(json.loads((ROOT/'deployment/oracle-host-setup-request.json').read_text()),evidence,os.environ)
    authorization=json.loads((ROOT/'deployment/oracle-groq-controlled-validation-request.json').read_text())
    validate_probe_authorization(authorization)
    payload={'mode':sys.argv[1],'evidence_sha256':approved['evidence_sha256'],'authorization':authorization}
    if sys.argv[1]=='reconcile-and-probe':
        payload['source']=(ROOT/'groq_usage_reconciliation.py').read_text()
        payload['sealed']=json.loads((ROOT/'deployment/oracle-groq-reconciliation.sealed.json').read_text())
    report=json.loads(run_pinned_command('sudo -n -- /opt/filip-guard/.venv/bin/python -c '+shlex.quote(REMOTE),operation='host-setup',input_data=json.dumps(payload).encode(),timeout=150))
    print(json.dumps(report,sort_keys=True))


if __name__=='__main__':
    try:main()
    except Exception:
        print('{"status":"recovery-operation-unverified","automatic_retries":0,"services_started":false}');raise SystemExit(1)
