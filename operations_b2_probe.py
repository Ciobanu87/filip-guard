"""Explicit B2 synthetic encrypted round-trip; never a production state backup.

One small retained object, no delete/list calls, no Groq or customer data. A
throwaway test-only encryption key travels to a fresh recovery process through
stdin, never argv/logs/artifacts. This does not provision a permanent host.
"""
import base64
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import tempfile
import uuid

from application_state_backup import export_application_state, recover_application_state, REVIEW_MARKER
from external_backup_store import S3BackupConfig, configured_s3_store


class ProbeStore:
    def __init__(self,store):self.store=store;self.puts=0;self.gets=0
    def put(self,key,data):
        if self.puts>=1 or not 0<len(data)<=65536:raise ValueError('Probe upload limit')
        self.puts+=1;self.store.put(key,data)
    def get(self,key):
        if self.gets>=3:raise ValueError('Probe download limit')
        self.gets+=1;data=self.store.get(key)
        if not 0<len(data)<=65536:raise ValueError('Probe download limit')
        return data


def configured_probe_store(env=None):
    env=os.environ if env is None else env
    if env.get('FG_B2_VALIDATE_AUTHORIZED')!='1':raise ValueError('Explicit synthetic probe authorization required')
    endpoint=env.get('FG_B2_ENDPOINT','')
    match=re.fullmatch(r'https://s3\.([a-z0-9-]+)\.backblazeb2\.com',endpoint)
    if not match:raise ValueError('Explicit B2 HTTPS endpoint required')
    values=(env.get('FG_B2_KEY_ID',''),env.get('FG_B2_APPLICATION_KEY',''))
    if any(not value.strip() or len(value)>4096 for value in values):raise ValueError('Explicit bucket-scoped credentials required')
    config=S3BackupConfig(endpoint,env.get('FG_B2_BUCKET',''),match[1])
    return ProbeStore(configured_s3_store(config,lambda:values))


def recover_probe(payload,store,destination):
    if type(payload) is not dict or set(payload)!={'manifest','test_key','expected_sha256'}:raise ValueError('Invalid probe receipt')
    key=base64.b64decode(payload['test_key'],validate=True)
    if len(key)!=32:raise ValueError('Invalid test-only key')
    result=recover_application_state(store,lambda version:key,payload['manifest'],destination)
    path=Path(destination)/'synthetic.sqlite'
    if sha256(path.read_bytes()).hexdigest()!=payload['expected_sha256']:raise ValueError('Recovered fixture differs')
    if not (Path(destination)/REVIEW_MARKER).is_file():raise ValueError('Recovery hold missing')
    return {'verified':result['verified'],'resume_blocked':result['resume_blocked']}


def run_probe(store, recover_process=None):
    recover_process=recover_process or _fresh_recovery
    with tempfile.TemporaryDirectory(prefix='fg-b2-synthetic-') as directory:
        root=Path(directory);source=root/'source';source.mkdir(mode=0o700)
        path=source/'synthetic.sqlite'
        with sqlite3.connect(path) as db:
            db.execute('CREATE TABLE synthetic_proof (value TEXT)')
            db.execute('INSERT INTO synthetic_proof VALUES (?)',('filip-guard-synthetic-recovery-only',))
        db.close()  # sqlite3's context manager commits but does not close.
        path.chmod(0o600)
        digest=sha256(path.read_bytes()).hexdigest();key=os.urandom(32)
        manifest=export_application_state(source,store,lambda version:key,
            deployment_id=uuid.uuid4().hex,key_id='disposable-probe-only',quiesced=True)
        # Recovery receives no original database path; only receipt and test key.
        source.rename(root/'quarantined-source')
        payload={'manifest':manifest,'test_key':base64.b64encode(key).decode(),'expected_sha256':digest}
        recovered=recover_process(payload)
        if recovered!={'verified':True,'resume_blocked':True}:raise ValueError('Independent recovery not verified')
    return {'status':'verified','scope':'synthetic-b2-recovery-only','external_roundtrip_verified':True,
        'fresh_process_recovery_verified':True,'production_backup_validated':False,
        'production_key_custody_validated':False,'permanent_host_provisioned':False,
        'groq_calls':0,'deletes':0,'retained_probe_objects':1}


def _fresh_recovery(payload):
    child=subprocess.run([sys.executable,str(Path(__file__).resolve()),'recover'],
        input=json.dumps(payload),text=True,capture_output=True,timeout=45,check=False)
    if child.returncode!=0:raise ValueError('Independent recovery failed; retained probe object needs review')
    return json.loads(child.stdout)


def main(argv=None):
    args=sys.argv[1:] if argv is None else argv
    try:
        if args not in (['run'],['recover']):raise ValueError('Explicit operation required')
        store=configured_probe_store()
        if args==['recover']:
            raw=sys.stdin.read(8193)
            if len(raw)>8192:raise ValueError('Bounded recovery receipt required')
            with tempfile.TemporaryDirectory(prefix='fg-b2-independent-') as directory:
                result=recover_probe(json.loads(raw),store,Path(directory)/'restored')
        else:result=run_probe(store)
    except Exception:
        print(json.dumps({'status':'blocked-or-failed','reason':'Synthetic B2 recovery not verified; no production readiness claim'}));return 1
    print(json.dumps(result));return 0


if __name__=='__main__':raise SystemExit(main())
