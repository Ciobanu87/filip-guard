"""Persistent AutoFix orchestration for a trusted conditional-write gateway.

Live WordPress execution stays disabled. This engine is exercised against an
isolated local fixture. A future gateway MUST authenticate, authorize the exact
resource, and enforce compare-and-swap atomically on the WordPress server.
Ordinary REST GET followed by POST does not satisfy that contract.
"""
from contextlib import contextmanager
from dataclasses import asdict
from difflib import unified_diff
from hashlib import sha256
from hmac import compare_digest
import json
import math
import sqlite3
import time
import uuid

from wordpress_approval_store import ApprovalStore
from wordpress_execution_gate import VerifiedChange, _origin
from wordpress_revision_guard import ResourceSnapshot, verify_unchanged, RevisionMismatchError


class LiveAutoFixDisabled(RuntimeError):
    pass


class DisabledWordPressGateway:
    def read_authorized(self, *args, **kwargs):
        raise LiveAutoFixDisabled('Live WordPress AutoFix is disabled')

    def compare_and_swap(self, *args, **kwargs):
        raise LiveAutoFixDisabled('Live WordPress AutoFix is disabled')


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True)


def _instant(now):
    value = time.time() if now is None else now
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError('Invalid timestamp')
    return value


class AutoFixEngine:
    """Use only trusted server session IDs/user IDs, never request-supplied identity.

    Plans and outcomes survive app restarts. No credentials are stored. Backups
    contain the affected resource content, not a complete WordPress site backup.
    The gateway is a trusted server dependency, never selected by client input.
    """
    def __init__(self, database_path, backup_manager, gateway=None, *, pre_write_validator=None, post_write_verifier=None):
        if any(callback is not None and not callable(callback) for callback in (pre_write_validator,post_write_verifier)):
            raise ValueError('Trusted verification callbacks required')
        self.pre_write_validator,self.post_write_verifier=pre_write_validator,post_write_verifier
        self.database_path = str(database_path)
        self.backups = backup_manager
        self.gateway = gateway if gateway is not None else DisabledWordPressGateway()
        self.approvals = ApprovalStore(self.database_path)
        with self._db() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS repair_plans (
                plan_id TEXT PRIMARY KEY, session_digest TEXT NOT NULL,
                user_id INTEGER NOT NULL, payload TEXT NOT NULL,
                expires_at REAL NOT NULL, state TEXT NOT NULL,
                approval_digest TEXT, approval_metadata TEXT, result TEXT
            )''')

    @contextmanager
    def _db(self):
        db = sqlite3.connect(self.database_path, timeout=10)
        try:
            with db:
                yield db
        finally:
            db.close()

    def _load(self, plan_id, user_id, session_id, now):
        if not isinstance(plan_id, str) or type(user_id) is not int or user_id <= 0:
            raise PermissionError('Invalid repair identity')
        session_digest = self.approvals._session_digest(session_id)
        with self._db() as db:
            db.row_factory = sqlite3.Row
            row = db.execute('SELECT * FROM repair_plans WHERE plan_id=?', (plan_id,)).fetchone()
        if (row is None or row['user_id'] != user_id
                or not compare_digest(row['session_digest'], session_digest)):
            raise PermissionError('Repair does not belong to this session')
        if not _instant(now) < row['expires_at']:
            raise PermissionError('Repair proposal expired; review a fresh snapshot')
        return row, json.loads(row['payload'])

    def propose(self, *, site_url, resource_type, resource_id, user_id, session_id,
                proposed_content, repair_type='content_replace', now=None):
        """Persist exact original/proposed content for review; never write remotely."""
        instant = _instant(now)
        digest = self.approvals._session_digest(session_id)
        host = _origin(site_url)
        site_url = 'https://' + host
        if (repair_type != 'content_replace' or resource_type not in ('post', 'page')
                or type(resource_id) is not int or resource_id <= 0
                or type(user_id) is not int or user_id <= 0
                or not isinstance(proposed_content, str)
                or len(proposed_content.encode('utf-8')) > 1_000_000):
            raise ValueError('Unsupported repair or invalid target')
        original = self.gateway.read_authorized(site_url, resource_type, resource_id, user_id)
        verify_unchanged(original, original)
        if (original.site_url, original.resource_type, original.resource_id) != (site_url, resource_type, resource_id):
            raise PermissionError('Gateway returned the wrong resource')
        from wordpress_compatibility import require_content_profile
        require_content_profile(original.content);require_content_profile(proposed_content)
        if proposed_content == original.content:
            raise ValueError('No content change')
        plan_id = uuid.uuid4().hex
        payload = dict(original=asdict(original), proposed_content=proposed_content,
                       repair_type=repair_type)
        with self._db() as db:
            db.execute('INSERT INTO repair_plans VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, NULL)',
                       (plan_id, digest, user_id, _json(payload), instant + 900, 'proposed'))
        return self.review(plan_id, user_id=user_id, session_id=session_id, now=instant)

    def review(self, plan_id, *, user_id, session_id, now=None):
        row, payload = self._load(plan_id, user_id, session_id, now)
        original = payload['original']
        diff = ''.join(unified_diff(original['content'].splitlines(keepends=True),
                                   payload['proposed_content'].splitlines(keepends=True),
                                   fromfile='original', tofile='proposed'))
        return dict(plan_id=plan_id, state=row['state'], original=original,
                    proposed_content=payload['proposed_content'], diff=diff,
                    changes_applied=False, backup_scope='resource_content_only')

    def approve(self, plan_id, *, user_id, session_id, confirmed=False, now=None):
        instant = _instant(now)
        row, payload = self._load(plan_id, user_id, session_id, instant)
        if confirmed is not True or row['state'] != 'proposed':
            raise PermissionError('Explicit approval of a fresh proposal required')
        snapshot = ResourceSnapshot(**payload['original'])
        observed = self.gateway.read_authorized(snapshot.site_url, snapshot.resource_type,
                                                snapshot.resource_id, user_id)
        verify_unchanged(snapshot, observed)
        approval = self.approvals.issue(site_url=snapshot.site_url,
            resource_id=snapshot.resource_id, user_id=user_id,
            original_content=snapshot.content, proposed_content=payload['proposed_content'],
            trusted_authorization=True, session_id=session_id, now=instant,
            ttl=min(300, row['expires_at'] - instant))
        metadata = asdict(approval)
        token = metadata.pop('approval_id')
        with self._db() as db:
            cursor = db.execute('''UPDATE repair_plans SET state='approved',
                approval_digest=?, approval_metadata=? WHERE plan_id=? AND state='proposed' ''',
                (sha256(token.encode()).hexdigest(), _json(metadata), plan_id))
            if cursor.rowcount != 1:
                raise PermissionError('Proposal already approved')
        return token

    def _finish(self, plan_id, status, backup_id, *, changes_applied, detail='', verified_snapshot=None):
        result = dict(plan_id=plan_id, status=status, backup_id=backup_id,
                      changes_applied=changes_applied, detail=detail,
                      backup_scope='resource_content_only',
                      requires_intervention=status not in ('applied', 'rolled_back', 'conflict'))
        if verified_snapshot is not None:
            result['verified_snapshot']=asdict(verified_snapshot)
        with self._db() as db:
            db.execute('UPDATE repair_plans SET state=?, result=? WHERE plan_id=?',
                       (status, _json(result), plan_id))
        if status in ('outcome_unknown','rollback_unverified','rollback_conflict'):
            from operations_events import record
            record('rollback' if status.startswith('rollback') else 'autofix','failed',plan_id)
        return result

    def status(self, plan_id, *, user_id, session_id, now=None):
        row, _ = self._load(plan_id, user_id, session_id, now)
        return json.loads(row['result']) if row['result'] else {
            'plan_id': plan_id, 'status': row['state'], 'changes_applied': None,
            'requires_intervention': row['state'] in ('preparing_backup','applying')}

    def apply(self, plan_id, approval_token, *, user_id, session_id, now=None):
        """Apply once; ambiguous failures never trigger a blind retry or rollback."""
        instant = _instant(now)
        row, payload = self._load(plan_id, user_id, session_id, instant)
        if (not isinstance(approval_token, str) or not row['approval_digest']
                or not compare_digest(sha256(approval_token.encode()).hexdigest(), row['approval_digest'])):
            raise PermissionError('Approval does not match this repair')
        if row['result']:
            return json.loads(row['result'])
        if row['state'] != 'approved':
            raise PermissionError('Repair is unapproved or execution needs recovery')
        original = ResourceSnapshot(**payload['original'])
        observed = self.gateway.read_authorized(original.site_url, original.resource_type,
                                                original.resource_id, user_id)
        verify_unchanged(original, observed)
        approval = VerifiedChange(**json.loads(row['approval_metadata']), approval_id=approval_token)
        # Validate expiry and binding before creating a backup.
        from wordpress_execution_gate import verify_prewrite
        verify_prewrite(approval, site_url=original.site_url, resource_id=original.resource_id,
                        user_id=user_id, current_content=observed.content,
                        proposed_content=payload['proposed_content'], now=instant)
        self.approvals.verify_session_binding(approval, session_id)
        if self.pre_write_validator is not None and self.pre_write_validator(plan_id,original,payload['proposed_content']) is not True:
            raise PermissionError('Production prewrite verification required')
        # Reserve before any external backup I/O, not only before the write.
        # A crashed preparation stays held across restarts; no duplicate upload.
        with self._db() as db:
            cursor = db.execute("UPDATE repair_plans SET state='preparing_backup', result=? WHERE plan_id=? AND state='approved'",
                (_json(dict(plan_id=plan_id, status='preparing_backup', backup_id=None,
                            changes_applied=False, requires_intervention=True)), plan_id))
            if cursor.rowcount != 1:
                raise PermissionError('Repair already claimed')
        backup_id = None
        try:
            backup_id = self.backups.create_backup(original.site_url, original.resource_id, original.content)
            with self._db() as db:
                db.execute("UPDATE repair_plans SET result=? WHERE plan_id=? AND state='preparing_backup'",
                    (_json(dict(plan_id=plan_id, status='preparing_backup', backup_id=backup_id,
                                changes_applied=False, requires_intervention=True)), plan_id))
            backup = self.backups.get_backup(backup_id)
            if (not backup or backup.get('site_url') != original.site_url
                    or backup.get('resource_id') != original.resource_id
                    or backup.get('content') != original.content
                    or backup.get('content_hash') != sha256(original.content.encode()).hexdigest()):
                raise RuntimeError('Persistent verified content backup required')
        except Exception:
            from operations_events import record
            record('backup','failed',plan_id)
            # No WordPress write was admitted. Preserve the existing explicit
            # caller retry contract; never retry here. Process death is different:
            # BaseException is deliberately not caught and keeps the durable hold.
            with self._db() as db:
                db.execute("UPDATE repair_plans SET state='approved', result=NULL WHERE plan_id=? AND state='preparing_backup'",(plan_id,))
            raise
        # External backup readback may outlast the approval; re-check wall time.
        # Failure after this boundary stays held, including a process death after
        # consumption and before the applying journal update.
        if self.pre_write_validator is not None and self.pre_write_validator(plan_id,original,payload['proposed_content']) is not True:
            raise PermissionError('Production admission changed during backup')
        self.approvals.consume_for_offline_review(approval, site_url=original.site_url,
            resource_id=original.resource_id, user_id=user_id, current_content=original.content,
            proposed_content=payload['proposed_content'], now=_instant(now), session_id=session_id)
        with self._db() as db:
            cursor = db.execute("UPDATE repair_plans SET state='applying', result=? WHERE plan_id=? AND state='preparing_backup'",
                                (_json(dict(plan_id=plan_id, status='applying', backup_id=backup_id,
                                            changes_applied=None, requires_intervention=True)), plan_id))
            if cursor.rowcount != 1:
                raise PermissionError('Repair already claimed')
        try:
            written = self.gateway.compare_and_swap(original, payload['proposed_content'],
                                                    user_id, operation_id=plan_id)
        except RevisionMismatchError:
            return self._finish(plan_id, 'conflict', backup_id, changes_applied=False)
        except Exception:
            return self._finish(plan_id, 'outcome_unknown', backup_id, changes_applied=None,
                                detail='Write outcome unknown. Reconcile server state before any retry.')
        try:
            verify_unchanged(written, written)
        except (RevisionMismatchError, ValueError, UnicodeError):
            return self._finish(plan_id, 'outcome_unknown', backup_id, changes_applied=None,
                                detail='Invalid write receipt; automatic rollback is unsafe.')
        if (type(written) is not ResourceSnapshot
                or (written.site_url, written.resource_type, written.resource_id, written.content) !=
                (original.site_url, original.resource_type, original.resource_id, payload['proposed_content'])
                or written.revision == original.revision):
            return self._finish(plan_id, 'outcome_unknown', backup_id, changes_applied=None,
                                detail='Invalid write receipt; automatic rollback is unsafe.')
        try:
            observed = self.gateway.read_authorized(original.site_url, original.resource_type,
                                                    original.resource_id, user_id)
            verify_unchanged(written, observed)
            if self.post_write_verifier is not None and self.post_write_verifier(plan_id,original,written,'apply') is not True:
                raise RuntimeError('Independent public verification failed')
        except Exception:
            # Rollback is conditional on the exact receipt, so a later edit wins.
            try:
                restored = self.gateway.compare_and_swap(written, backup['content'], user_id,
                                                         operation_id=plan_id + ':rollback')
                if (type(restored) is not ResourceSnapshot
                        or (restored.site_url, restored.resource_type, restored.resource_id, restored.content) !=
                        (original.site_url, original.resource_type, original.resource_id, original.content)
                        or restored.revision == written.revision):
                    raise RuntimeError('Invalid rollback receipt')
                verify_unchanged(restored, self.gateway.read_authorized(
                    original.site_url, original.resource_type, original.resource_id, user_id))
                if self.post_write_verifier is not None and self.post_write_verifier(plan_id,written,restored,'rollback') is not True:
                    raise RuntimeError('Independent rollback verification failed')
            except RevisionMismatchError:
                return self._finish(plan_id, 'rollback_conflict', backup_id, changes_applied=None,
                                    detail='Concurrent edit preserved; restoration not completed.')
            except Exception:
                return self._finish(plan_id, 'rollback_unverified', backup_id, changes_applied=None,
                                    detail='Restoration could not be verified. Manual recovery required.')
            return self._finish(plan_id, 'rolled_back', backup_id, changes_applied=False)
        return self._finish(plan_id, 'applied', backup_id, changes_applied=True, verified_snapshot=written)
