"""Offline, durable, session-bound, single-use approval registry for future FILIP GUARD AutoFix.

Only trusted server code may issue approvals. This module does not authenticate
users, prove capabilities, connect to WordPress, or execute website writes.
"""
import math
from contextlib import contextmanager
import secrets
import sqlite3
import time
from hashlib import sha256

from wordpress_execution_gate import VerifiedChange, verify_prewrite, _origin


class ApprovalStore:
    def __init__(self, database_path):
        self.database_path = str(database_path)
        with self._db() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS approvals (
                approval_digest TEXT PRIMARY KEY,
                site TEXT NOT NULL, resource_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL, original_hash TEXT NOT NULL,
                proposed_hash TEXT NOT NULL, approved_at REAL NOT NULL,
                expires_at REAL NOT NULL, consumed_at REAL
            )''')
            columns = {row[1] for row in db.execute('PRAGMA table_info(approvals)')}
            if 'session_digest' not in columns:
                db.execute('ALTER TABLE approvals ADD COLUMN session_digest TEXT')

    @contextmanager
    def _db(self):
        db = sqlite3.connect(self.database_path, timeout=10)
        try:
            db.execute('PRAGMA busy_timeout=10000')
            with db:
                yield db
        finally:
            db.close()

    def issue(self, *, site_url, resource_id, user_id, original_content,
              proposed_content, trusted_authorization=False, now=None, ttl=300, session_id=None):
        """Server-side-only issuance; caller must independently authenticate and authorize.

        The trusted_authorization flag is NOT itself proof of authorization.
        session_id must be a high-entropy ID from the authenticated server session.
        Pre-migration approvals without session binding cannot be consumed.
        Do not expose this method to untrusted requests or user-supplied flags.
        """
        if trusted_authorization is not True:
            raise PermissionError('Trusted authorization required')
        if type(resource_id) is not int or resource_id <= 0 or type(user_id) is not int or user_id <= 0:
            raise ValueError('Invalid user or resource')
        if not isinstance(original_content, str) or not isinstance(proposed_content, str):
            raise ValueError('Invalid content')
        if original_content == proposed_content:
            raise ValueError('No change')
        if isinstance(ttl, bool) or not isinstance(ttl, (int, float)) or not math.isfinite(ttl) or not 0 < ttl <= 900:
            raise ValueError('Invalid TTL')
        instant = time.time() if now is None else now
        if isinstance(instant, bool) or not isinstance(instant, (int, float)) or not math.isfinite(instant):
            raise ValueError('Invalid timestamp')
        session_digest = self._session_digest(session_id)
        site = _origin(site_url)
        token = secrets.token_urlsafe(32)
        approval = VerifiedChange(site_url, resource_id, user_id,
            sha256(original_content.encode()).hexdigest(),
            sha256(proposed_content.encode()).hexdigest(),
            instant, instant + ttl, token)
        with self._db() as db:
            db.execute('''INSERT INTO approvals
                (approval_digest, site, resource_id, user_id, original_hash,
                 proposed_hash, approved_at, expires_at, consumed_at, session_digest)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, ?)''',
                (sha256(token.encode()).hexdigest(), site, resource_id, user_id,
                 approval.original_hash, approval.proposed_hash, instant, instant + ttl, session_digest))
        return approval

    def consume_for_offline_review(self, approval, *, site_url, resource_id, user_id,
                                   current_content, proposed_content, now=None, session_id=None):
        """Atomically consume a matching approval; NEVER performs a website write.

        Must NOT be treated as an atomic WordPress content check: live content
        could change after this local operation. Future writes need a remote CAS.
        """
        instant = time.time() if now is None else now
        if isinstance(instant, bool) or not isinstance(instant, (int, float)) or not math.isfinite(instant):
            raise ValueError('Invalid timestamp')
        session_digest = self._session_digest(session_id)
        verify_prewrite(approval, site_url=site_url, resource_id=resource_id,
            user_id=user_id, current_content=current_content,
            proposed_content=proposed_content, now=instant)
        with self._db() as db:
            cursor = db.execute('''UPDATE approvals SET consumed_at=?
                WHERE approval_digest=? AND site=? AND resource_id=? AND user_id=?
                AND original_hash=? AND proposed_hash=? AND approved_at=?
                AND expires_at=? AND consumed_at IS NULL AND expires_at>?
                AND session_digest=?''',
                (instant, sha256(approval.approval_id.encode()).hexdigest(),
                 _origin(site_url), resource_id, user_id, approval.original_hash,
                 approval.proposed_hash, approval.approved_at, approval.expires_at, instant, session_digest))
            if cursor.rowcount != 1:
                raise PermissionError('Approval absent, expired or already consumed')
        return {'approved_for_offline_review': True, 'changes_applied': False}

    def verify_session_binding(self, approval, session_id):
        """Check session before backup creation; consumption remains atomic later."""
        digest = self._session_digest(session_id)
        if not isinstance(approval, VerifiedChange):
            raise PermissionError('Missing verified approval')
        with self._db() as db:
            row = db.execute(
                'SELECT 1 FROM approvals WHERE approval_digest=? '
                'AND session_digest=? AND consumed_at IS NULL',
                (sha256(approval.approval_id.encode()).hexdigest(), digest)).fetchone()
        if row is None:
            raise PermissionError('Approval not bound to active session or already consumed')
        return True

    @staticmethod
    def _session_digest(session_id):
        # Must come from the authenticated server session, never a request field.
        if not isinstance(session_id, str) or not 32 <= len(session_id) <= 512:
            raise PermissionError('Authenticated server session required')
        return sha256(session_id.encode('utf-8')).hexdigest()
