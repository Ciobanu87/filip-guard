"""Local customer identity and opaque server sessions; no WordPress credentials.

Passwords use salted scrypt; only session-token digests are stored. Production
TLS, signup policy and deployment remain separate. Optional verified-contact
recovery is implemented in customer_recovery and disabled by default.
"""
from contextlib import contextmanager
from dataclasses import dataclass
from hashlib import scrypt, sha256
from hmac import compare_digest
import math
import os
from pathlib import Path
import re
import secrets
import sqlite3
import time
import uuid


class AuthenticationError(PermissionError):
    pass


@dataclass(frozen=True)
class CustomerPrincipal:
    customer_id: str
    username: str


def instant(now=None):
    value = time.time() if now is None else now
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError('Invalid timestamp')
    return value


def private_database(path):
    path = Path(path)
    if any((parent / 'FG-RESTORE-REVIEW-REQUIRED').exists() for parent in path.absolute().parents):
        raise ValueError('Recovered application state requires operator reconciliation before resume')
    if str(path) == ':memory:' or path.is_symlink():
        raise ValueError('Private persistent database path required')
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
    except FileExistsError:
        if not path.is_file() or path.stat().st_mode & 0o077:
            raise ValueError('Database must be a private regular file')
    return str(path)


class CustomerAuth:
    def __init__(self, database_path, *, session_ttl=3600, idle_ttl=900):
        if (type(session_ttl) is not int or type(idle_ttl) is not int
                or not 0 < idle_ttl <= session_ttl <= 86400):
            raise ValueError('Invalid session lifetime')
        self.path = private_database(database_path)
        self.session_ttl, self.idle_ttl = session_ttl, idle_ttl
        with self.db() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS customers (
                customer_id TEXT PRIMARY KEY, username TEXT NOT NULL UNIQUE,
                salt BLOB NOT NULL, password_hash BLOB NOT NULL, active INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS customer_sessions (
                token_digest TEXT PRIMARY KEY, customer_id TEXT NOT NULL,
                created_at REAL NOT NULL, expires_at REAL NOT NULL, last_seen REAL NOT NULL,
                revoked INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS login_attempts (
                login_digest TEXT PRIMARY KEY, failures INTEGER NOT NULL, locked_until REAL NOT NULL);
            ''')

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def _username(username):
        if type(username) is not str:
            raise AuthenticationError('Invalid account credentials')
        name = username.strip().lower()
        if not re.fullmatch(r'[a-z0-9_.-]{3,64}', name):
            raise AuthenticationError('Invalid account credentials')
        return name

    @staticmethod
    def _password(password, *, registering=False):
        if (type(password) is not str or not 1 <= len(password.encode('utf-8')) <= 1024
                or (registering and len(password) < 12)):
            raise AuthenticationError('Account password must contain 12 or more characters' if registering
                                      else 'Invalid account credentials')
        return password.encode('utf-8')

    @staticmethod
    def token_digest(token):
        if type(token) is not str or not re.fullmatch(r'[A-Za-z0-9_-]{43}', token):
            raise AuthenticationError('Session invalid or expired')
        return sha256(token.encode('ascii')).hexdigest()

    def register(self, username, password):
        name = self._username(username)
        raw = self._password(password, registering=True)
        salt = secrets.token_bytes(16)
        digest = scrypt(raw, salt=salt, n=16384, r=8, p=1, dklen=64)
        customer_id = uuid.uuid4().hex
        try:
            with self.db() as db:
                db.execute('INSERT INTO customers VALUES (?, ?, ?, ?, 1)', (customer_id, name, salt, digest))
        except sqlite3.IntegrityError:
            raise AuthenticationError('Account cannot be created with these details') from None
        return CustomerPrincipal(customer_id, name)

    def login(self, username, password, *, now=None):
        timestamp = instant(now)
        name = self._username(username)
        raw = self._password(password)
        login_digest = sha256(name.encode()).hexdigest()
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            attempt = db.execute('SELECT * FROM login_attempts WHERE login_digest=?', (login_digest,)).fetchone()
            if attempt and timestamp < attempt['locked_until']:
                raise AuthenticationError('Invalid account credentials or login temporarily unavailable')
            row = db.execute('SELECT * FROM customers WHERE username=?', (name,)).fetchone()
            # Equal-cost password derivation also for an unknown username.
            actual = scrypt(raw, salt=bytes(row['salt']) if row else b'\x00' * 16,
                            n=16384, r=8, p=1, dklen=64)
            valid = row is not None and row['active'] == 1 and compare_digest(actual, bytes(row['password_hash']))
            if not valid:
                failures = (attempt['failures'] if attempt and timestamp < attempt['locked_until'] + 60 else 0) + 1
                db.execute('INSERT OR REPLACE INTO login_attempts VALUES (?, ?, ?)',
                           (login_digest, failures, timestamp + 60 if failures >= 5 else timestamp))
            else:
                db.execute('DELETE FROM login_attempts WHERE login_digest=?', (login_digest,))
                token = secrets.token_urlsafe(32)
                db.execute('INSERT INTO customer_sessions VALUES (?, ?, ?, ?, ?, 0)',
                           (self.token_digest(token), row['customer_id'], timestamp,
                            timestamp + self.session_ttl, timestamp))
        if not valid:
            raise AuthenticationError('Invalid account credentials or login temporarily unavailable')
        return token

    def resolve(self, token, *, now=None, touch=True):
        timestamp = instant(now)
        digest = self.token_digest(token)
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('''SELECT s.*, c.username, c.active FROM customer_sessions s
                JOIN customers c ON c.customer_id=s.customer_id WHERE token_digest=?''', (digest,)).fetchone()
            if (row is None or row['revoked'] or row['active'] != 1
                    or not row['created_at'] <= timestamp < row['expires_at']
                    or not 0 <= timestamp - row['last_seen'] < self.idle_ttl):
                raise AuthenticationError('Session invalid or expired')
            if touch:
                db.execute('UPDATE customer_sessions SET last_seen=? WHERE token_digest=?', (timestamp, digest))
        return CustomerPrincipal(row['customer_id'], row['username'])

    def logout(self, token):
        digest = self.token_digest(token)
        with self.db() as db:
            db.execute('UPDATE customer_sessions SET revoked=1 WHERE token_digest=?', (digest,))

    def change_password(self, token, current_password, new_password, *, now=None):
        timestamp = instant(now)
        principal = self.resolve(token, now=timestamp)
        current = self._password(current_password)
        new = self._password(new_password, registering=True)
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            session = db.execute('SELECT * FROM customer_sessions WHERE token_digest=? AND customer_id=?',
                                 (self.token_digest(token), principal.customer_id)).fetchone()
            row = db.execute('SELECT * FROM customers WHERE customer_id=?', (principal.customer_id,)).fetchone()
            if (row is None or row['active'] != 1 or session is None or session['revoked']
                    or not session['created_at'] <= timestamp < session['expires_at']
                    or not 0 <= timestamp - session['last_seen'] < self.idle_ttl):
                raise AuthenticationError('Session invalid or expired')
            if not compare_digest(scrypt(current, salt=bytes(row['salt']), n=16384, r=8, p=1, dklen=64),
                                  bytes(row['password_hash'])):
                raise AuthenticationError('Invalid account credentials')
            salt = secrets.token_bytes(16)
            digest = scrypt(new, salt=salt, n=16384, r=8, p=1, dklen=64)
            db.execute('UPDATE customers SET salt=?, password_hash=? WHERE customer_id=?',
                       (salt, digest, principal.customer_id))
            db.execute('UPDATE customer_sessions SET revoked=1 WHERE customer_id=?', (principal.customer_id,))
