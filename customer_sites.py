"""Customer-owned site workspaces, encrypted credentials and authenticated AutoFix.

The default live gateway is disabled. Trusted server code may inject the reviewed
REST gateway for isolated validation. No site credentials are exposed to the UI.
"""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import uuid

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from customer_auth import private_database, instant
from external_backup_store import ScopedObjectStore
from verified_external_backups import VerifiedExternalBackups
from wordpress_auth_preflight import validate_auth_preflight
from wordpress_execution_gate import _origin
from wordpress_autofix_engine import AutoFixEngine, LiveAutoFixDisabled


class CustomerSites:
    def __init__(self, auth, root, master_keys, *, active_key_id='development', object_store=None,
                 gateway_factory=None):
        self.auth,self.root,self.master_keys=auth,Path(root),master_keys
        self.key_id,self.object_store,self.gateway_factory=active_key_id,object_store,gateway_factory
        if not re.fullmatch('[A-Za-z0-9_-]{1,64}',active_key_id):raise ValueError('Invalid key identifier')
        self.root.mkdir(parents=True,exist_ok=True,mode=0o700)
        if self.root.stat().st_mode & 0o077:raise ValueError('Private customer data root required')
        self.registry=private_database(self.root/'sites.sqlite')
        with self.db() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS customer_sites (
                site_id TEXT PRIMARY KEY, customer_id TEXT NOT NULL, origin TEXT NOT NULL UNIQUE,
                wordpress_user_id INTEGER NOT NULL, key_id TEXT NOT NULL,
                credentials BLOB NOT NULL, verified_at REAL NOT NULL)''')

    @contextmanager
    def db(self):
        db=sqlite3.connect(self.registry,timeout=10);db.row_factory=sqlite3.Row
        try:
            with db:yield db
        finally:db.close()

    def _derive(self, customer_id,site_id,key_id,purpose):
        if not callable(self.master_keys):raise PermissionError('External master key custody is not configured')
        try:
            key=self.master_keys(key_id)
        except Exception:
            raise PermissionError('Externally managed master key unavailable') from None
        if type(key) is not bytes or len(key)!=32:raise PermissionError('Invalid externally managed master key')
        return HKDF(algorithm=hashes.SHA256(),length=32,salt=None,
            info=('FILIP-GUARD/v1/'+purpose+'/'+customer_id+'/'+site_id).encode()).derive(key)

    @staticmethod
    def _aad(customer_id,site_id,origin,wordpress_user_id):
        return json.dumps([customer_id,site_id,origin,wordpress_user_id],separators=(',',':')).encode()

    def _owned(self,session,site_id,*,now=None):
        principal=self.auth.resolve(session,now=now)
        if type(site_id) is not str or not re.fullmatch('[0-9a-f]{32}',site_id):
            raise PermissionError('Site unavailable for this account')
        with self.db() as db:
            row=db.execute('SELECT * FROM customer_sites WHERE site_id=? AND customer_id=?',
                (site_id,principal.customer_id)).fetchone()
        if row is None:raise PermissionError('Site unavailable for this account')
        return principal,row

    def list_sites(self,session,*,now=None):
        principal=self.auth.resolve(session,now=now)
        with self.db() as db:
            rows=db.execute('SELECT site_id,origin FROM customer_sites WHERE customer_id=? ORDER BY origin',
                (principal.customer_id,)).fetchall()
        return [dict(row) for row in rows]

    def connect(self,session,site_url,username,application_password,*,now=None):
        principal=self.auth.resolve(session,now=now)
        checked=validate_auth_preflight(site_url,username,application_password)
        origin='https://'+checked.hostname
        site_id=uuid.uuid4().hex
        key=self._derive(principal.customer_id,site_id,self.key_id,'credentials')
        if self.gateway_factory is None:raise LiveAutoFixDisabled('Customer site connections are disabled')
        gateway=self.gateway_factory(origin,lambda:(username,application_password))
        wordpress_user_id=gateway.verify_site_owner()
        if type(wordpress_user_id) is not int or wordpress_user_id<=0:
            raise PermissionError('Verified WordPress site ownership required')
        # Re-check the session after the remote verification, before persisting any secret.
        if self.auth.resolve(session,now=now).customer_id!=principal.customer_id:
            raise PermissionError('Authenticated account changed')
        plaintext=json.dumps(dict(username=username,application_password=application_password),separators=(',',':')).encode()
        nonce=secrets.token_bytes(12)
        encrypted=nonce+AESGCM(key).encrypt(nonce,plaintext,self._aad(principal.customer_id,site_id,origin,wordpress_user_id))
        try:
            with self.db() as db:
                db.execute('INSERT INTO customer_sites VALUES (?, ?, ?, ?, ?, ?, ?)',
                    (site_id,principal.customer_id,origin,wordpress_user_id,self.key_id,encrypted,instant(now)))
        except sqlite3.IntegrityError:
            raise PermissionError('Site connection is unavailable for this account') from None
        return {'site_id':site_id,'origin':origin}

    def _credentials(self,session,site_id,*,now=None):
        principal,row=self._owned(session,site_id,now=now)
        encrypted=bytes(row['credentials'])
        key=self._derive(principal.customer_id,site_id,row['key_id'],'credentials')
        try:
            decoded=AESGCM(key).decrypt(encrypted[:12],encrypted[12:],
                self._aad(principal.customer_id,site_id,row['origin'],row['wordpress_user_id']))
            data=json.loads(decoded)
            validate_auth_preflight(row['origin'],data['username'],data['application_password'])
        except Exception:
            raise PermissionError('Stored WordPress credentials could not be authenticated') from None
        return data['username'],data['application_password']

    def _workspace(self,principal,site_id):
        # Both components are server-issued opaque hex IDs, never URLs or request paths.
        path=self.root/'customers'/principal.customer_id/'sites'/site_id
        path.mkdir(parents=True,exist_ok=True,mode=0o700)
        return path

    def _context(self,session,site_id,*,now=None,require_external=False):
        principal,row=self._owned(session,site_id,now=now)
        if self.gateway_factory is None:raise LiveAutoFixDisabled('Customer AutoFix is disabled')
        if require_external and self.object_store is None:
            raise PermissionError('Verified external backup storage is not configured')
        key_provider=lambda key_id:self._derive(principal.customer_id,site_id,key_id,'content-backups')
        key_provider(row['key_id'])
        path=self._workspace(principal,site_id)
        scoped=ScopedObjectStore(self.object_store,principal.customer_id,site_id) if self.object_store is not None else None
        backups=VerifiedExternalBackups(path/'backups.sqlite',path/'receipts.sqlite',row['origin'],scoped,
            key_provider,key_id=row['key_id'])
        service=self
        class AuthorizedGateway:
            def _gateway(self,site,kind,resource,user_id):
                _,current=service._owned(session,site_id,now=now)
                if site!=current['origin'] or user_id!=current['wordpress_user_id']:
                    raise PermissionError('Customer WordPress target mismatch')
                return service.gateway_factory(current['origin'],lambda:service._credentials(session,site_id,now=now))
            def read_authorized(self,site,kind,resource,user_id):
                return self._gateway(site,kind,resource,user_id).read_authorized(site,kind,resource,user_id)
            def compare_and_swap(self,expected,content,user_id,*,operation_id):
                return self._gateway(expected.site_url,expected.resource_type,expected.resource_id,user_id).compare_and_swap(
                    expected,content,user_id,operation_id=operation_id)
        engine=AutoFixEngine(private_database(path/'repairs.sqlite'),backups,AuthorizedGateway())
        return engine,dict(user_id=row['wordpress_user_id'],session_id=session,now=now),row

    def propose(self,session,site_id,resource_type,resource_id,proposed_content,*,now=None):
        engine,identity,row=self._context(session,site_id,now=now)
        return engine.propose(site_url=row['origin'],resource_type=resource_type,resource_id=resource_id,
                              proposed_content=proposed_content,**identity)

    def review(self,session,site_id,plan_id,*,now=None):
        engine,identity,_=self._context(session,site_id,now=now)
        return engine.review(plan_id,**identity)

    def approve(self,session,site_id,plan_id,*,confirmed=False,now=None):
        engine,identity,_=self._context(session,site_id,now=now)
        return engine.approve(plan_id,confirmed=confirmed,**identity)

    def apply(self,session,site_id,plan_id,approval_token,*,now=None):
        engine,identity,_=self._context(session,site_id,now=now,require_external=True)
        return engine.apply(plan_id,approval_token,**identity)

    def get_backup(self,session,site_id,backup_id,*,now=None):
        engine,_,_=self._context(session,site_id,now=now,require_external=True)
        return engine.backups.get_backup(backup_id)

    def resources(self,session,site_id,*,now=None):
        _,row=self._owned(session,site_id,now=now)
        if self.gateway_factory is None:raise LiveAutoFixDisabled('Customer site connections are disabled')
        gateway=self.gateway_factory(row['origin'],lambda:self._credentials(session,site_id,now=now))
        return gateway.list_repair_resources(row['wordpress_user_id'])

    def read_resource(self,session,site_id,kind,resource_id,*,now=None):
        engine,identity,row=self._context(session,site_id,now=now)
        return engine.gateway.read_authorized(row['origin'],kind,resource_id,identity['user_id'])

    def repair_record(self,session,site_id,plan_id,*,now=None):
        # Authenticated owner history survives login/session expiry; it cannot approve/apply.
        engine,_,_=self._context(session,site_id,now=now)
        with engine._db() as db:
            row=db.execute('SELECT payload,state,result FROM repair_plans WHERE plan_id=?',(plan_id,)).fetchone()
        if row is None:raise PermissionError('Repair history unavailable for this site')
        return dict(plan_id=plan_id,payload=json.loads(row[0]),state=row[1],result=json.loads(row[2]) if row[2] else None)
