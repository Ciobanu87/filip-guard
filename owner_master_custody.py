#!/opt/filip-guard/.venv/bin/python
"""Explicit owner-operated encrypted custody; no service/network/AI activation."""
import base64
import getpass
import fcntl
import hashlib
import hmac
import json
import os
from pathlib import Path
import pwd
import re
import resource
import sqlite3
import stat
import subprocess
import sys
import tempfile
import uuid
import warnings

sys.path.insert(0,'/opt/filip-guard')
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from application_state_backup import export_application_state

ITERATIONS=600000
CONFIG=Path('/etc/filip-guard')
CUSTODY=CONFIG/'custody'
KEYRING=CONFIG/'secrets/keyring'
KEY_ID='oracle-v1'


def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':')).encode('ascii')
def b64(value):return base64.b64encode(value).decode('ascii')

def validate_secret(secret):
    if type(secret) is not str or not re.fullmatch(r'[A-Za-z0-9_-]{43}',secret) or len(set(secret))<16:
        raise ValueError('Use the 43-character random secret generated on your own device')
    return secret.encode('ascii')


def aad(key_id,deployment_id):
    return ('FILIP-GUARD/owner-master-custody/v1/'+key_id+'/'+deployment_id+'/PBKDF2-SHA256/600000').encode()


def create_bundle(master,secret,*,deployment_id,key_id=KEY_ID):
    if type(master) is not bytes or len(master)!=32:raise ValueError('256-bit master required')
    if not re.fullmatch('[0-9a-f]{32}',deployment_id) or not re.fullmatch('[A-Za-z0-9_-]{1,64}',key_id):raise ValueError('Invalid custody binding')
    password=validate_secret(secret)
    salt=os.urandom(16);nonce=os.urandom(12)
    wrapping=PBKDF2HMAC(algorithm=hashes.SHA256(),length=32,salt=salt,iterations=ITERATIONS).derive(password)
    envelope={'format':'filip-guard-master-envelope-v1','key_id':key_id,'deployment_id':deployment_id,
              'kdf':'PBKDF2-SHA256','iterations':ITERATIONS,'salt':b64(salt),'nonce':b64(nonce),
              'ciphertext':b64(AESGCM(wrapping).encrypt(nonce,master,aad(key_id,deployment_id)))}
    # Validate the actual existing application backup/recovery format using
    # disposable SQLite only. Never inspect/change production application state.
    challenge=base64.urlsafe_b64encode(os.urandom(32)).decode().rstrip('=')
    class LocalStore:
        def __init__(self):self.data={}
        def put(self,name,value):self.data[name]=value
        def get(self,name):return self.data[name]
    store=LocalStore()
    with tempfile.TemporaryDirectory(prefix='fg-owner-custody-fixture-') as temporary:
        root=Path(temporary);root.chmod(0o700)
        path=root/'custody.sqlite';db=sqlite3.connect(path)
        try:
            db.execute('PRAGMA page_size=512');db.execute('VACUUM')
            db.execute('CREATE TABLE custody (value TEXT NOT NULL)')
            db.execute('INSERT INTO custody VALUES (?)',('FG-CUSTODY-CHALLENGE:'+challenge,));db.commit()
        finally:db.close()
        path.chmod(0o600)
        manifest=export_application_state(root,store,lambda requested:master if requested==key_id else None,
                                          deployment_id=deployment_id,key_id=key_id,quiesced=True)
    bundle={'format':'filip-guard-owner-custody-v1','envelope':envelope,
            'application_state_check':{'manifest':manifest,'ciphertext':b64(store.get(manifest['object_id']))}}
    encoded=canonical(bundle)
    if len(encoded)>3800:raise ValueError('Custody export exceeds fixed safe transport bound')
    digest=hashlib.sha256(encoded).hexdigest()
    proof=hmac.new(master,b'FG-OWNER-CUSTODY-PROOF/v1\0'+bytes.fromhex(digest)+challenge.encode(),hashlib.sha256).hexdigest()
    # Server-side round trip is necessary but explicitly NOT owner custody proof.
    recovered=AESGCM(wrapping).decrypt(nonce,base64.b64decode(envelope['ciphertext']),aad(key_id,deployment_id))
    if not hmac.compare_digest(recovered,master):raise ValueError('Envelope round trip failed')
    return encoded,proof


def private(path,*,directory=False,owner=0):
    info=path.lstat()
    if (not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode))
        or info.st_uid!=owner or info.st_mode&(0o022 if directory else 0o077)
        or (not directory and info.st_nlink!=1)):raise ValueError('Private controlled path required')
    return info


def exclusive(path,data,mode=0o600,uid=0,gid=0):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,mode)
    with os.fdopen(fd,'wb') as output:
        output.write(data);output.flush();os.fsync(output.fileno());os.fchown(output.fileno(),uid,gid);os.fchmod(output.fileno(),mode)
    directory=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(directory)
    finally:os.close(directory)


def held_configuration():
    if os.geteuid()!=0:raise ValueError('Root operator operation required')
    private(CONFIG,directory=True);private(CONFIG/'runtime.env')
    settings={}
    for line in (CONFIG/'runtime.env').read_text().splitlines():
        if not line or line.startswith('#') or '=' not in line:continue
        name,value=line.split('=',1)
        if name in settings:raise ValueError('Duplicate configuration')
        settings[name]=value
    if settings.get('FG_AI_AUTHORIZED')!='0' or settings.get('FG_STATE_BACKUP_AUTHORIZED')!='0':raise ValueError('Services must remain held')
    for unit in ('filip-guard-ui.service','filip-guard-worker.service','filip-guard-state-backup.service','filip-guard-state-backup.timer'):
        result=subprocess.run(['/usr/bin/systemctl','is-active',unit],capture_output=True,text=True,timeout=10)
        if result.stdout.strip()!='inactive':raise ValueError('All services must stay inactive')
        enabled=subprocess.run(['/usr/bin/systemctl','is-enabled',unit],capture_output=True,text=True,timeout=10)
        if enabled.stdout.strip() not in ('disabled','static'):raise ValueError('All services must stay disabled')
    return settings


def prompt(label):
    if not os.isatty(0) or not os.isatty(2):raise ValueError('Owner private interactive SSH terminal required')
    with warnings.catch_warnings():
        warnings.simplefilter('error',getpass.GetPassWarning)
        return getpass.getpass(label)


def prepare():
    settings=held_configuration();user=pwd.getpwnam('filipguard')
    for path in Path('/proc').iterdir():
        if path.name.isdecimal():
            try:
                if path.stat().st_uid==user.pw_uid:raise ValueError('No unrelated app-user process may run during first-key preparation')
            except FileNotFoundError:pass
    if CUSTODY.exists():
        if private(CUSTODY,directory=True).st_mode&0o077:raise ValueError('Private custody directory required')
        if (CUSTODY/'pending.json').exists() or (CUSTODY/'bundle.sealed.json').exists():
            raise ValueError('Existing custody preparation is never regenerated; export the existing sealed bundle')
    if KEYRING.exists():
        if private(KEYRING,directory=True,owner=user.pw_uid).st_mode&0o077:raise ValueError('Private app key directory required')
        if KEYRING.is_symlink() or list(KEYRING.iterdir()):raise ValueError('Existing key versions require separate recovery review')
    if settings.get('FG_GUARD_KEY_ID') or settings.get('FG_GUARD_MASTER_KEY_FILE'):
        raise ValueError('Existing master-key configuration is never replaced')
    if settings.get('FG_GUARD_KEY_DIRECTORY') not in (None,str(KEYRING)):raise ValueError('Different key directory')
    deployment=settings.get('FG_DEPLOYMENT_ID') or uuid.uuid4().hex
    if not re.fullmatch('[0-9a-f]{32}',deployment):raise ValueError('Invalid existing deployment identifier')
    first=prompt('Secretul aleator de recuperare (43 caractere, ascuns): ')
    second=prompt('Repeta secretul (caracterele nu sunt afisate): ')
    validate_secret(first)
    if not hmac.compare_digest(first,second):raise ValueError('Secret entries do not match; no key generated')
    # Creation happens ONLY during this explicit owner-interactive command.
    master=os.urandom(32);encoded,expected=create_bundle(master,first,deployment_id=deployment)
    first=second=None
    private(CONFIG/'secrets',directory=True)
    if not KEYRING.exists():KEYRING.mkdir(mode=0o700);os.chown(KEYRING,user.pw_uid,user.pw_gid)
    if not CUSTODY.exists():CUSTODY.mkdir(mode=0o700)
    key_path=KEYRING/(KEY_ID+'.key')
    new_key=new_bundle=False;committed=False
    try:
        exclusive(key_path,master,0o400,user.pw_uid,user.pw_gid);new_key=True
        exclusive(CUSTODY/'bundle.sealed.json',encoded);new_bundle=True
        record={'status':'owner-offline-recovery-pending','key_id':KEY_ID,'deployment_id':deployment,
                'bundle_sha256':hashlib.sha256(encoded).hexdigest(),'expected_owner_proof':expected,
                'master_sha256_private':hashlib.sha256(master).hexdigest()}
        exclusive(CUSTODY/'pending.json',canonical(record))
        env_path=CONFIG/'runtime.env';original=env_path.read_text()
        additions={'FG_GUARD_KEY_ID':KEY_ID,'FG_DEPLOYMENT_ID':deployment,'FG_GUARD_KEY_DIRECTORY':str(KEYRING)}
        for name,value in additions.items():
            if name in settings and settings[name]!=value:raise ValueError('Existing configuration differs')
        text=original+('' if original.endswith('\n') else '\n')+''.join(name+'='+value+'\n' for name,value in additions.items() if name not in settings)
        fd,temporary=tempfile.mkstemp(prefix='.fg-custody-config-',dir=CONFIG)
        try:
            with os.fdopen(fd,'w') as output:output.write(text);output.flush();os.fsync(output.fileno());os.fchmod(output.fileno(),0o600)
            os.replace(temporary,env_path);committed=True
            directory=os.open(CONFIG,os.O_RDONLY|os.O_DIRECTORY)
            try:os.fsync(directory)
            finally:os.close(directory)
        finally:
            if os.path.exists(temporary):os.unlink(temporary)
    except Exception:
        if not committed:
            if new_key:key_path.unlink(missing_ok=True)
            if new_bundle:(CUSTODY/'bundle.sealed.json').unlink(missing_ok=True)
            (CUSTODY/'pending.json').unlink(missing_ok=True)
        raise
    finally:master=None;expected=None
    return {'status':'master-installed-owner-custody-still-pending','master_file_mode':'0400',
            'local_application_backup_recovery_verified':True,'independent_owner_recovery_verified':False,
            'groq_api_calls':0,'b2_api_calls':0,'services_started':False}


def export_sealed():
    held_configuration()
    if not (CUSTODY/'pending.json').exists():return {'status':'awaiting-owner-interactive-custody-preparation','services_started':False}
    private(CUSTODY,directory=True);private(CUSTODY/'pending.json');private(CUSTODY/'bundle.sealed.json')
    record=json.loads((CUSTODY/'pending.json').read_text());encoded=(CUSTODY/'bundle.sealed.json').read_bytes()
    if len(encoded)>3800 or hashlib.sha256(encoded).hexdigest()!=record['bundle_sha256']:raise ValueError('Custody bundle integrity failure')
    bundle=json.loads(encoded)
    if set(bundle)!={'format','envelope','application_state_check'} or bundle['format']!='filip-guard-owner-custody-v1':raise ValueError('Only sealed custody format may leave Oracle')
    if set(bundle['envelope'])!={'format','key_id','deployment_id','kdf','iterations','salt','nonce','ciphertext'} or set(bundle['application_state_check'])!={'manifest','ciphertext'}:raise ValueError('Unexpected fields are never exported')
    if len(base64.b64decode(bundle['envelope']['ciphertext'],validate=True))!=48:raise ValueError('Only encrypted 256-bit master may leave Oracle')
    return {'status':'encrypted-owner-custody-export','bundle':bundle,'services_started':False}


def verify_owner():
    held_configuration();private(CUSTODY,directory=True);private(CUSTODY/'pending.json')
    record=json.loads((CUSTODY/'pending.json').read_text())
    proof=prompt('Codul de verificare generat LOCAL pe telefon (64 caractere, ascuns): ')
    if not re.fullmatch('[0-9a-f]{64}',proof) or not hmac.compare_digest(proof,record['expected_owner_proof']):raise ValueError('Independent owner recovery proof mismatch')
    user=pwd.getpwnam('filipguard');path=KEYRING/(record['key_id']+'.key');private(path,owner=user.pw_uid)
    if stat.S_IMODE(path.stat().st_mode)!=0o400:raise ValueError('Read-only master required')
    from operator_secrets import private_file
    if not hmac.compare_digest(hashlib.sha256(private_file(path,32)).hexdigest(),record['master_sha256_private']):raise ValueError('Installed master changed')
    receipt={'status':'independent-owner-custody-verified','bundle_sha256':record['bundle_sha256'],
             'owner_controls_decryption_secret':True,'offline_application_backup_recovery_verified':True,
             'services_started':False}
    path=CUSTODY/'owner-verified.json'
    if path.exists():
        private(path)
        if json.loads(path.read_text())!=receipt:raise ValueError('Different existing custody receipt')
    else:exclusive(path,canonical(receipt))
    return receipt



def status():
    settings=held_configuration()
    if not (CUSTODY/'pending.json').exists():
        return {'status':'owner-custody-not-yet-prepared','master_prepared_by_this_workflow':False,'services_started':False}
    private(CUSTODY,directory=True);private(CUSTODY/'pending.json')
    record=json.loads((CUSTODY/'pending.json').read_text());user=pwd.getpwnam('filipguard')
    path=KEYRING/(record['key_id']+'.key');info=private(path,owner=user.pw_uid)
    from operator_secrets import private_file
    installed=stat.S_IMODE(info.st_mode)==0o400 and info.st_size==32 and hmac.compare_digest(hashlib.sha256(private_file(path,32)).hexdigest(),record['master_sha256_private'])
    verified=False
    if (CUSTODY/'owner-verified.json').exists():
        private(CUSTODY/'owner-verified.json')
        receipt=json.loads((CUSTODY/'owner-verified.json').read_text())
        verified=(receipt.get('status')=='independent-owner-custody-verified' and receipt.get('bundle_sha256')==record['bundle_sha256'])
    bound=settings.get('FG_GUARD_KEY_ID')==record['key_id'] and settings.get('FG_DEPLOYMENT_ID')==record['deployment_id']
    return {'status':'owner-custody-status-verified','master_installed_private':installed,
            'runtime_binding_matches':bound,'independent_owner_custody_verified':installed and bound and verified,
            'groq_api_calls':0,'b2_api_calls':0,'services_started':False}

def main():
    resource.setrlimit(resource.RLIMIT_CORE,(0,0));os.umask(0o077)
    if len(sys.argv)!=2:raise ValueError('Explicit custody operation required')
    if os.geteuid()!=0:raise ValueError('Root operator required')
    private(CONFIG,directory=True)
    fd=os.open(CONFIG/'custody-operation.lock',os.O_WRONLY|os.O_CREAT|os.O_NOFOLLOW,0o600)
    try:
        info=os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid!=0 or info.st_mode&0o077 or info.st_nlink!=1:raise ValueError('Private operation lock required')
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if sys.argv[1]=='prepare':result=prepare()
        elif sys.argv[1]=='export-sealed':result=export_sealed()
        elif sys.argv[1]=='verify-owner':result=verify_owner()
        elif sys.argv[1]=='status':result=status()
        else:raise ValueError('Unsupported custody operation')
    finally:os.close(fd)
    print(json.dumps(result,sort_keys=True))


if __name__=='__main__':
    try:main()
    except (Exception,KeyboardInterrupt):
        print('{"status":"custody-operation-held-or-failed","services_started":false,"secret_values_printed":false}')
        raise SystemExit(1)
