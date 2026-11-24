"""Additive read-only domain ownership directory; WordPress ownership unchanged.

Public file challenges contain no password/API key. Only digests are stored;
proofs are short-lived, single-use, rate limited, owner-bound and HTTPS verified.
No credential, site transfer, DNS write or WordPress mutation is performed.
"""
from contextlib import contextmanager
from hashlib import sha256
from hmac import compare_digest
import secrets
import sqlite3
import uuid

from customer_auth import private_database,instant
from guard_network import GuardNetwork
from guard_module_contract import configure

PROOF_PATH='/.well-known/filip-guard-verification.txt'
PROOF_SECONDS=900
OWNERSHIP_SECONDS=30*86400


class GuardAssetDirectory:
    def __init__(self,wordpress_directory,*,clock=instant,reader=None):
        self.wordpress=wordpress_directory;self.auth=wordpress_directory.auth;self.root=wordpress_directory.root
        self.path=private_database(self.root/'guard-assets.sqlite');self.clock=clock
        self.reader=reader or (lambda origin:GuardNetwork(origin,max_seconds=8).site(PROOF_PATH))
        with self.asset_db() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS guard_assets (
                site_id TEXT PRIMARY KEY,customer_id TEXT NOT NULL,origin TEXT NOT NULL UNIQUE,
                guard_kind TEXT NOT NULL,verified_until REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS guard_proofs (
                customer_id TEXT NOT NULL,origin TEXT NOT NULL,guard_kind TEXT NOT NULL,
                digest TEXT NOT NULL,expires REAL NOT NULL,state TEXT NOT NULL,
                PRIMARY KEY(customer_id,origin));
                CREATE TABLE IF NOT EXISTS guard_proof_attempts (
                attempt_id TEXT PRIMARY KEY,customer_id TEXT NOT NULL,attempted_at REAL NOT NULL);
                CREATE INDEX IF NOT EXISTS guard_proof_rate ON guard_proof_attempts(customer_id,attempted_at);''')

    def __getattr__(self,name):return getattr(self.wordpress,name)

    @contextmanager
    def asset_db(self):
        db=sqlite3.connect(self.path,timeout=5);db.row_factory=sqlite3.Row
        try:
            with db:yield db
        finally:db.close()

    def _time(self,now):return self.clock() if now is None else instant(now)

    def _existing_wordpress(self,origin):
        with self.wordpress.db() as db:
            row=db.execute('SELECT customer_id FROM customer_sites WHERE origin=?',(origin,)).fetchone()
        return row[0] if row else None

    def begin_proof(self,session,origin,kind,*,now=None):
        timestamp=self._time(now);principal=self.auth.resolve(session,now=timestamp)
        configure(origin,{'website':True})
        if kind not in ('website','commerce','api','infrastructure'):raise ValueError('Unsupported read-only guard kind')
        owner=self._existing_wordpress(origin)
        if owner is not None:
            if owner!=principal.customer_id:raise PermissionError('Origin is already bound to an authorized account')
            raise ValueError('Use the existing WordPress site; no second ownership proof is needed')
        token='filip-guard-'+secrets.token_urlsafe(32);digest=sha256(token.encode()).hexdigest()
        with self.asset_db() as db:
            db.execute('BEGIN IMMEDIATE')
            old=db.execute('SELECT customer_id FROM guard_assets WHERE origin=?',(origin,)).fetchone()
            if old and old[0]!=principal.customer_id:raise PermissionError('Origin is already bound to another account')
            pending=db.execute("SELECT COUNT(*) FROM guard_proofs WHERE customer_id=? AND state!='verified' AND expires>?",(principal.customer_id,timestamp)).fetchone()[0]
            if pending>=10:raise ValueError('Too many pending ownership checks')
            db.execute("INSERT INTO guard_proofs VALUES (?,?,?,?,?,'pending') ON CONFLICT(customer_id,origin) DO UPDATE SET guard_kind=excluded.guard_kind,digest=excluded.digest,expires=excluded.expires,state='pending'",
                       (principal.customer_id,origin,kind,digest,timestamp+PROOF_SECONDS))
        return {'origin':origin,'path':PROOF_PATH,'token':token,'expires_at':timestamp+PROOF_SECONDS}

    def confirm_proof(self,session,origin,token,*,now=None):
        timestamp=self._time(now);principal=self.auth.resolve(session,now=timestamp)
        configure(origin,{'website':True})
        if type(token) is not str or not 40<=len(token)<=100:raise PermissionError('Ownership proof unavailable')
        digest=sha256(token.encode()).hexdigest()
        with self.asset_db() as db:
            db.execute('BEGIN IMMEDIATE')
            proof=db.execute('SELECT * FROM guard_proofs WHERE customer_id=? AND origin=?',(principal.customer_id,origin)).fetchone()
            if (not proof or proof['state']!='pending' or not timestamp<proof['expires'] or not compare_digest(proof['digest'],digest)):
                raise PermissionError('Ownership proof invalid, expired or already used')
            attempts=db.execute('SELECT COUNT(*),MAX(attempted_at) FROM guard_proof_attempts WHERE customer_id=? AND attempted_at>?',
                                (principal.customer_id,timestamp-3600)).fetchone()
            if attempts[0]>=5 or (attempts[1] is not None and timestamp-attempts[1]<60):raise ValueError('Ownership-check rate limit reached')
            db.execute('INSERT INTO guard_proof_attempts VALUES (?,?,?)',(uuid.uuid4().hex,principal.customer_id,timestamp))
            db.execute("UPDATE guard_proofs SET state='checking' WHERE customer_id=? AND origin=?",(principal.customer_id,origin))
        try:
            status,kind,body=self.reader(origin)
            if status!=200 or kind!='text/plain' or len(body)>128 or not compare_digest(body.strip(),token.encode()):
                raise ValueError('Verification file does not match')
            timestamp=self._time(now);self.auth.resolve(session,now=timestamp)
            if self._existing_wordpress(origin) is not None:raise PermissionError('Origin ownership changed')
            with self.asset_db() as db:
                db.execute('BEGIN IMMEDIATE')
                current=db.execute('SELECT * FROM guard_proofs WHERE customer_id=? AND origin=?',(principal.customer_id,origin)).fetchone()
                if not current or current['digest']!=digest or current['state']!='checking' or not timestamp<current['expires']:
                    raise PermissionError('Ownership proof changed or expired')
                existing=db.execute('SELECT * FROM guard_assets WHERE origin=?',(origin,)).fetchone()
                if existing and existing['customer_id']!=principal.customer_id:raise PermissionError('Origin is already bound')
                site_id=existing['site_id'] if existing else uuid.uuid4().hex
                if existing:
                    db.execute('UPDATE guard_assets SET guard_kind=?,verified_until=? WHERE site_id=?',(proof['guard_kind'],timestamp+OWNERSHIP_SECONDS,site_id))
                else:db.execute('INSERT INTO guard_assets VALUES (?,?,?,?,?)',(site_id,principal.customer_id,origin,proof['guard_kind'],timestamp+OWNERSHIP_SECONDS))
                db.execute("UPDATE guard_proofs SET state='verified' WHERE customer_id=? AND origin=?",(principal.customer_id,origin))
            return {'site_id':site_id,'origin':origin,'verified_until':timestamp+OWNERSHIP_SECONDS,'guard_kind':proof['guard_kind']}
        except Exception:
            with self.asset_db() as db:
                db.execute("UPDATE guard_proofs SET state='pending' WHERE customer_id=? AND origin=? AND digest=? AND state='checking'",(principal.customer_id,origin,digest))
            raise PermissionError('Secure domain-control verification could not be completed') from None

    def _owned(self,session,site_id,*,now=None):
        timestamp=self._time(now);principal=self.auth.resolve(session,now=timestamp)
        with self.asset_db() as db:row=db.execute('SELECT * FROM guard_assets WHERE site_id=?',(site_id,)).fetchone()
        if row:
            if row['customer_id']!=principal.customer_id or not timestamp<row['verified_until'] or self._existing_wordpress(row['origin']) not in (None,principal.customer_id):raise PermissionError('Asset ownership proof unavailable or expired')
            return principal,dict(row)
        return self.wordpress._owned(session,site_id,now=timestamp)

    def list_sites(self,session,*,now=None):
        timestamp=self._time(now);principal=self.auth.resolve(session,now=timestamp)
        with self.asset_db() as db:
            rows=db.execute('SELECT * FROM guard_assets WHERE customer_id=? AND verified_until>? ORDER BY origin',(principal.customer_id,timestamp)).fetchall()
        return self.wordpress.list_sites(session,now=timestamp)+[dict(row) for row in rows]

    def monitoring_binding(self,customer_id,site_id,origin):
        with self.asset_db() as db:row=db.execute('SELECT * FROM guard_assets WHERE site_id=?',(site_id,)).fetchone()
        if row:return (row['customer_id']==customer_id and row['origin']==origin and self.clock()<row['verified_until']
                       and self._existing_wordpress(origin) in (None,customer_id))
        with self.wordpress.db() as db:
            return bool(db.execute('SELECT 1 FROM customer_sites WHERE customer_id=? AND site_id=? AND origin=?',(customer_id,site_id,origin)).fetchone())
