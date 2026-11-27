"""Opt-in verified contact and password recovery; encrypted delivery, no network."""
import json
import secrets
import uuid
from hashlib import sha256,scrypt
from hmac import compare_digest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes
from customer_auth import AuthenticationError,instant
from monitoring_email import _address

ACK={'status':'accepted-if-eligible'}


class AccountRecovery:
    def __init__(self,auth,keys,*,key_id,authorized=False):
        if authorized is not True:raise ValueError('Explicit account-recovery authorization required')
        self.auth,self.keys,self.key_id=auth,keys,key_id
        if len(keys(key_id))!=32:raise ValueError('Existing retained master required')
        with auth.db() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS account_contacts (
                customer_id TEXT PRIMARY KEY,verified_email TEXT UNIQUE,pending_email TEXT,epoch INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS account_challenges (
                challenge_id TEXT PRIMARY KEY,customer_id TEXT NOT NULL,purpose TEXT NOT NULL,
                token_hash TEXT UNIQUE NOT NULL,recipient TEXT NOT NULL,epoch INTEGER NOT NULL,
                created_at REAL NOT NULL,expires_at REAL NOT NULL,consumed INTEGER NOT NULL,
                delivery_state TEXT NOT NULL,key_id TEXT NOT NULL,payload BLOB,credential_version TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS account_action_limits (
                subject TEXT NOT NULL,bucket INTEGER NOT NULL,attempts INTEGER NOT NULL,PRIMARY KEY(subject,bucket));''')

    def _key(self,key_id):
        return HKDF(algorithm=hashes.SHA256(),length=32,salt=None,info=b'FILIP-GUARD/v1/account-mail').derive(self.keys(key_id))

    @staticmethod
    def _aad(row):
        return json.dumps([row['challenge_id'],row['customer_id'],row['purpose'],row['recipient'],row['epoch'],row['credential_version']],separators=(',',':')).encode()

    def _limit(self,db,subject,purpose,now):
        bucket=int(now//3600);db.execute('DELETE FROM account_action_limits WHERE bucket<?',(bucket-48,))
        for key,limit in [('global:'+purpose,30),(sha256((purpose+':'+subject).encode()).hexdigest(),3)]:
            db.execute('INSERT OR IGNORE INTO account_action_limits VALUES (?,?,0)',(key,bucket))
            count=db.execute('SELECT attempts FROM account_action_limits WHERE subject=? AND bucket=?',(key,bucket)).fetchone()[0]
            if count>=limit:return False
            db.execute('UPDATE account_action_limits SET attempts=attempts+1 WHERE subject=? AND bucket=?',(key,bucket))
        return True

    def _issue(self,db,customer,purpose,recipient,epoch,now):
        db.execute('UPDATE account_challenges SET consumed=1,payload=NULL WHERE customer_id=? AND purpose=?',(customer,purpose))
        token=secrets.token_urlsafe(32)
        account=db.execute('SELECT password_hash FROM customers WHERE customer_id=?',(customer,)).fetchone()
        row={'challenge_id':uuid.uuid4().hex,'customer_id':customer,'purpose':purpose,'recipient':recipient,'epoch':epoch,
             'credential_version':sha256(bytes(account['password_hash'])).hexdigest()}
        nonce=secrets.token_bytes(12)
        payload=nonce+AESGCM(self._key(self.key_id)).encrypt(nonce,json.dumps({'token':token}).encode(),self._aad(row))
        db.execute('INSERT INTO account_challenges VALUES (?,?,?,?,?,?,?,?,0,?,?,?,?)',
            (row['challenge_id'],customer,purpose,sha256(token.encode()).hexdigest(),recipient,epoch,now,now+900,'pending',self.key_id,payload,row['credential_version']))

    def request_verification(self,session,password,address,*,now=None):
        timestamp=instant(now);principal=self.auth.resolve(session,now=timestamp)
        validated=_address(address);local,domain=validated.rsplit('@',1);email=local+'@'+domain.lower();raw=self.auth._password(password)
        with self.auth.db() as db:
            db.execute('BEGIN IMMEDIATE')
            allowed=self._limit(db,principal.customer_id,'verify',timestamp)
        if not allowed:raise AuthenticationError('Account request unavailable')
        with self.auth.db() as db:account=db.execute('SELECT * FROM customers WHERE customer_id=? AND active=1',(principal.customer_id,)).fetchone()
        if account is None or not compare_digest(scrypt(raw,salt=bytes(account['salt']),n=16384,r=8,p=1,dklen=64),bytes(account['password_hash'])):
            raise AuthenticationError('Account request unavailable')
        self.auth.resolve(session,now=timestamp)
        with self.auth.db() as db:
            db.execute('BEGIN IMMEDIATE')
            current=db.execute('SELECT * FROM customers WHERE customer_id=? AND active=1',(principal.customer_id,)).fetchone()
            session_row=db.execute('SELECT * FROM customer_sessions WHERE token_digest=? AND customer_id=?',(self.auth.token_digest(session),principal.customer_id)).fetchone()
            if not session_row or session_row['revoked'] or not session_row['created_at']<=timestamp<session_row['expires_at']:raise AuthenticationError('Account request unavailable')
            if current is None or current['password_hash']!=account['password_hash']:raise AuthenticationError('Account request unavailable')
            contact=db.execute('SELECT * FROM account_contacts WHERE customer_id=?',(principal.customer_id,)).fetchone()
            if contact and contact['verified_email'] and contact['verified_email']!=email:raise AuthenticationError('Verified address changes require separate review')
            epoch=contact['epoch']+1 if contact else 1
            db.execute('INSERT INTO account_contacts VALUES (?,?,?,?) ON CONFLICT(customer_id) DO UPDATE SET pending_email=excluded.pending_email,epoch=excluded.epoch',
                (principal.customer_id,None,email,epoch))
            db.execute('UPDATE account_challenges SET consumed=1,payload=NULL WHERE customer_id=?',(principal.customer_id,))
            self._issue(db,principal.customer_id,'verify',email,epoch,timestamp)
        return dict(ACK)

    def request_recovery(self,username,*,now=None):
        timestamp=instant(now)
        try:name=self.auth._username(username)
        except AuthenticationError:name='!'
        with self.auth.db() as db:
            db.execute('BEGIN IMMEDIATE')
            allowed=self._limit(db,name,'recover',timestamp)
            contact=db.execute('SELECT c.customer_id,a.verified_email,a.epoch FROM customers c JOIN account_contacts a ON a.customer_id=c.customer_id WHERE c.username=? AND c.active=1',(name,)).fetchone()
            if allowed and contact and contact['verified_email']:
                self._issue(db,contact['customer_id'],'recover',contact['verified_email'],contact['epoch'],timestamp)
        return dict(ACK)

    def _challenge(self,db,token,purpose,now):
        digest=self.auth.token_digest(token)
        row=db.execute('SELECT * FROM account_challenges WHERE token_hash=? AND purpose=?',(digest,purpose)).fetchone()
        if row is None or row['consumed'] or not row['created_at']<=now<row['expires_at']:raise AuthenticationError('Code invalid or expired')
        contact=db.execute('SELECT * FROM account_contacts WHERE customer_id=?',(row['customer_id'],)).fetchone()
        active=db.execute('SELECT active,password_hash FROM customers WHERE customer_id=?',(row['customer_id'],)).fetchone()
        field='pending_email' if purpose=='verify' else 'verified_email'
        if not active or active['active']!=1 or sha256(bytes(active['password_hash'])).hexdigest()!=row['credential_version'] or not contact or contact['epoch']!=row['epoch'] or contact[field]!=row['recipient']:
            raise AuthenticationError('Code invalid or expired')
        return row

    def confirm_verification(self,token,*,now=None):
        timestamp=instant(now)
        try:
            with self.auth.db() as db:
                db.execute('BEGIN IMMEDIATE');row=self._challenge(db,token,'verify',timestamp)
                db.execute('UPDATE account_contacts SET verified_email=pending_email,pending_email=NULL,epoch=epoch+1 WHERE customer_id=?',(row['customer_id'],))
                db.execute('UPDATE account_challenges SET consumed=1,payload=NULL WHERE customer_id=?',(row['customer_id'],))
        except Exception:raise AuthenticationError('Code invalid or expired') from None
        return {'status':'email-verified'}

    def reset_password(self,token,new_password,*,now=None):
        timestamp=instant(now);raw=self.auth._password(new_password,registering=True)
        with self.auth.db() as db:
            db.execute('BEGIN IMMEDIATE');row=self._challenge(db,token,'recover',timestamp)
            salt=secrets.token_bytes(16);digest=scrypt(raw,salt=salt,n=16384,r=8,p=1,dklen=64)
            db.execute('UPDATE customers SET salt=?,password_hash=? WHERE customer_id=?',(salt,digest,row['customer_id']))
            db.execute('UPDATE customer_sessions SET revoked=1 WHERE customer_id=?',(row['customer_id'],))
            db.execute('UPDATE account_contacts SET pending_email=NULL,epoch=epoch+1 WHERE customer_id=?',(row['customer_id'],))
            db.execute('UPDATE account_challenges SET consumed=1,payload=NULL WHERE customer_id=?',(row['customer_id'],))
        return {'status':'password-reset-sign-in-required'}

    def dispatch_once(self,sender=None,*,now=None):
        if sender is None:return {'status':'disabled'}
        timestamp=instant(now)
        with self.auth.db() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute("UPDATE account_challenges SET consumed=1,payload=NULL WHERE expires_at<=?",(timestamp,))
            row=db.execute("SELECT * FROM account_challenges WHERE delivery_state='pending' AND consumed=0 ORDER BY created_at,challenge_id LIMIT 1").fetchone()
            if row is None:return {'status':'idle'}
            db.execute("UPDATE account_challenges SET delivery_state='sending' WHERE challenge_id=?",(row['challenge_id'],))
        try:
            encrypted=bytes(row['payload']);data=json.loads(AESGCM(self._key(row['key_id'])).decrypt(encrypted[:12],encrypted[12:],self._aad(row)))
            with self.auth.db() as db:self._challenge(db,data['token'],row['purpose'],timestamp)
            sender.send_account_challenge({'challenge_id':row['challenge_id'],'customer_id':row['customer_id'],'purpose':row['purpose'],'address':row['recipient'],'token':data['token']})
        except Exception:status='unknown'
        else:status='sent'
        with self.auth.db() as db:db.execute('UPDATE account_challenges SET delivery_state=?,payload=NULL WHERE challenge_id=?',(status,row['challenge_id']))
        return {'status':status}
