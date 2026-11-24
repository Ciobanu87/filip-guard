"""Operator-only non-destructive external probe / independent content recovery.

No implicit network, real key generation, deletion or WordPress writes. Receipt
and mounted master-key custody must survive separately from the Streamlit host.
"""
import argparse
import json
from pathlib import Path
import re
import secrets
import tempfile
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from backup import BackupManager
from external_backup_store import ScopedObjectStore
from infrastructure_configuration import configured_external_store
from operator_secrets import configured_master_keys,private_file
from wordpress_encrypted_backup import export_encrypted_copy,restore_encrypted_copy


def probe_external_backup(store):
    # Only synthetic content and a short-lived test key. Never a production key.
    with tempfile.TemporaryDirectory(prefix='fg-storage-probe-') as root:
        root=Path(root);key=secrets.token_bytes(32)
        source=BackupManager(root/'source.sqlite')
        identifier=source.create_backup('https://storage-probe.test',1,'FILIP GUARD synthetic recovery probe')
        receipt=export_encrypted_copy(source,store,key,key_id='ephemeral-probe')
        recovered=root/'independent.sqlite'
        result=restore_encrypted_copy(store.get(receipt.object_id),key,recovered,expected_sha256=receipt.ciphertext_sha256)
        if BackupManager(recovered).get_backup(identifier)['content']!='FILIP GUARD synthetic recovery probe':
            raise ValueError('Independent recovery failed')
        return {'status':'verified','scope':result['scope'],'independent_recovery':True,
                'object_id':receipt.object_id,'production_data':False}


def recover_customer_archive(store,master_keys,manifest,destination):
    # Trusted receipt copy: never infer object ID, key or account from ciphertext.
    cid,sid=manifest['customer_id'],manifest['site_id']
    if any(type(x) is not str or not re.fullmatch('[0-9a-f]{32}',x) for x in (cid,sid)):
        raise ValueError('Trusted customer/site recovery metadata required')
    if manifest.get('scope')!='resource_content_only':raise ValueError('Content recovery scope required')
    if type(manifest.get('ciphertext_sha256')) is not str or not re.fullmatch('[0-9a-f]{64}',manifest['ciphertext_sha256']):
        raise ValueError('Trusted ciphertext digest required')
    master=master_keys(manifest['key_id'])
    key=HKDF(algorithm=hashes.SHA256(),length=32,salt=None,
        info=('FILIP-GUARD/v1/content-backups/'+cid+'/'+sid).encode()).derive(master)
    ciphertext=ScopedObjectStore(store,cid,sid).get(manifest['object_id'])
    return restore_encrypted_copy(ciphertext,key,destination,expected_sha256=manifest['ciphertext_sha256'])


def main(argv=None):
    parser=argparse.ArgumentParser(description='Authorized external content-backup verification; never writes WordPress')
    parser.add_argument('operation',choices=['probe','recover'])
    parser.add_argument('--authorized-external-access',action='store_true')
    parser.add_argument('--manifest');parser.add_argument('--destination')
    args=parser.parse_args(argv)
    if not args.authorized_external_access:
        print(json.dumps({'status':'blocked','reason':'Explicit operator authorization required'}));return 2
    try:
        if args.operation=='recover':
            if not args.manifest or not args.destination:raise ValueError()
            # Refuse an existing destination before any external call.
            if Path(args.destination).exists() or Path(args.destination).is_symlink():raise ValueError()
            manifest=json.loads(private_file(args.manifest,8192));keys=configured_master_keys()
            result=recover_customer_archive(configured_external_store(),keys,manifest,args.destination)
            result={'status':'verified',**result}
        else:result=probe_external_backup(configured_external_store())
    except Exception:
        print(json.dumps({'status':'failed','reason':'External backup or recovery could not be verified'}));return 1
    print(json.dumps(result));return 0

if __name__=='__main__':raise SystemExit(main())
