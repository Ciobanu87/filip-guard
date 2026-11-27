"""Offline owner-only unseal into a NEW private key file on a trusted recovery host.

No original Oracle host/database, network, service start, stdout key or Library.
"""
import argparse
import base64
import getpass
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import stat
import warnings
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def unseal(bundle_bytes,secret):
    if not isinstance(bundle_bytes,bytes) or len(bundle_bytes)>3800 or not re.fullmatch(r'[A-Za-z0-9_-]{43}',secret):raise ValueError('Invalid bounded input')
    def unique(pairs):
        result={}
        for key,value in pairs:
            if key in result:raise ValueError('Duplicate envelope field')
            result[key]=value
        return result
    bundle=json.loads(bundle_bytes,object_pairs_hook=unique)
    if set(bundle)!={'format','envelope','application_state_check'} or bundle['format']!='filip-guard-owner-custody-v1':raise ValueError('Unknown custody format')
    e=bundle['envelope']
    if set(e)!={'format','key_id','deployment_id','kdf','iterations','salt','nonce','ciphertext'}:raise ValueError('Unexpected envelope fields')
    if (e['format']!='filip-guard-master-envelope-v1' or e['kdf']!='PBKDF2-SHA256' or type(e['iterations']) is not int or e['iterations']!=600000
        or not re.fullmatch('[A-Za-z0-9_-]{1,64}',e['key_id']) or not re.fullmatch('[0-9a-f]{32}',e['deployment_id'])):raise ValueError('Unreviewed envelope parameters')
    salt=base64.b64decode(e['salt'],validate=True);nonce=base64.b64decode(e['nonce'],validate=True);ciphertext=base64.b64decode(e['ciphertext'],validate=True)
    if (len(salt),len(nonce),len(ciphertext))!=(16,12,48):raise ValueError('Invalid encrypted-key lengths')
    wrapping=hashlib.pbkdf2_hmac('sha256',secret.encode('ascii'),salt,600000,dklen=32)
    aad=('FILIP-GUARD/owner-master-custody/v1/'+e['key_id']+'/'+e['deployment_id']+'/PBKDF2-SHA256/600000').encode()
    master=AESGCM(wrapping).decrypt(nonce,ciphertext,aad)
    if len(master)!=32:raise ValueError('Invalid master length')
    return master,{'key_id':e['key_id'],'deployment_id':e['deployment_id']}


def recover_private_file(bundle_bytes,secret,destination):
    path=Path(destination).absolute();parent=path.parent
    if any(p.is_symlink() for p in (parent,*parent.parents)):raise ValueError('Private non-symlink recovery directory required')
    info=parent.stat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid!=os.geteuid() or info.st_mode&0o077:raise ValueError('Owner-controlled 0700 recovery directory required')
    master,metadata=unseal(bundle_bytes,secret)
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o400)
    try:
        with os.fdopen(fd,'wb') as output:
            output.write(master);output.flush();os.fsync(output.fileno());os.fchmod(output.fileno(),0o400)
        directory=os.open(parent,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(directory)
        finally:os.close(directory)
    except Exception:path.unlink(missing_ok=True);raise
    finally:master=None
    return {'status':'master-recovered-into-new-private-file','file_mode':'0400',**metadata,'services_started':False}


def main():
    parser=argparse.ArgumentParser(description='Owner offline custody recovery; no overwrite or network')
    parser.add_argument('--bundle',required=True);parser.add_argument('--destination',required=True)
    parser.add_argument('--confirm-new-trusted-recovery-host',action='store_true')
    args=parser.parse_args()
    if not args.confirm_new_trusted_recovery_host or not os.isatty(0) or not os.isatty(2):raise ValueError('Explicit trusted-host confirmation and owner interactive terminal required')
    resource.setrlimit(resource.RLIMIT_CORE,(0,0));os.umask(0o077)
    with warnings.catch_warnings():
        warnings.simplefilter('error',getpass.GetPassWarning)
        secret=getpass.getpass('Owner recovery secret (hidden): ')
    data=Path(args.bundle).read_bytes()
    result=recover_private_file(data,secret,args.destination);secret=None
    print(json.dumps(result,sort_keys=True))


if __name__=='__main__':
    try:main()
    except (Exception,KeyboardInterrupt):
        print('{"status":"offline-key-recovery-held-or-failed","services_started":false,"secret_values_printed":false}')
        raise SystemExit(1)
