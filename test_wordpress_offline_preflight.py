import os
import tempfile
import unittest
from unittest.mock import Mock

from wordpress_approval_store import ApprovalStore
from wordpress_offline_preflight import OfflinePreflight
from sqlite_test_utils import test_db
from hashlib import sha256

class BackupManager:
    """Test-only persistent backup implementation; production uses backup.py."""
    def __init__(self, path):
        self.path = path
        with test_db(path) as db:
            db.execute('CREATE TABLE backups (id INTEGER PRIMARY KEY, site TEXT, resource INTEGER, content TEXT, digest TEXT)')
    def create_backup(self, site_url, resource_id, content):
        with test_db(self.path) as db:
            cursor = db.execute('INSERT INTO backups(site, resource, content, digest) VALUES (?,?,?,?)',
                (site_url, resource_id, content, sha256(content.encode()).hexdigest()))
            return str(cursor.lastrowid)
    def get_backup(self, backup_id):
        with test_db(self.path) as db:
            row = db.execute('SELECT site, resource, content, digest FROM backups WHERE id=?', (backup_id,)).fetchone()
        if row is None:
            return None
        return dict(site_url=row[0], resource_id=row[1], content=row[2], content_hash=row[3])


class OfflinePreflightTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = ApprovalStore(os.path.join(self.tmp.name, 'approvals.db'))
        self.backup = BackupManager(os.path.join(self.tmp.name, 'backups.db'))
        self.preflight = OfflinePreflight(self.store, self.backup)
        self.kw = dict(site_url='https://example.com', resource_id=10, user_id=7,
                       current_content='original', proposed_content='revised', now=1000, session_id='a' * 43)
        self.approval = self.store.issue(site_url=self.kw['site_url'],
            resource_id=10, user_id=7, original_content='original',
            proposed_content='revised', trusted_authorization=True, now=1000, session_id='a' * 43)

    def test_success_read_only_with_verified_backup(self):
        result = self.preflight.prepare(self.approval, **self.kw)
        self.assertFalse(result['changes_applied'])
        self.assertEqual(self.backup.get_backup(result['backup_id'])['content'], 'original')

    def test_replay_rejected(self):
        self.preflight.prepare(self.approval, **self.kw)
        with self.assertRaises(PermissionError):
            self.preflight.prepare(self.approval, **self.kw)

    def test_stale_content_rejected(self):
        with self.assertRaises(PermissionError):
            self.preflight.prepare(self.approval, **(self.kw | {'current_content': 'changed'}))

    def test_wrong_user_rejected(self):
        with self.assertRaises(PermissionError):
            self.preflight.prepare(self.approval, **(self.kw | {'user_id': 8}))

    def test_backup_failure_does_not_consume_approval(self):
        broken = Mock()
        broken.create_backup.return_value = 'fake'
        broken.get_backup.return_value = None
        with self.assertRaises(RuntimeError):
            OfflinePreflight(self.store, broken).prepare(self.approval, **self.kw)
        self.assertFalse(self.preflight.prepare(self.approval, **self.kw)['changes_applied'])

    def test_corrupted_backup_does_not_consume_approval(self):
        broken = Mock()
        broken.create_backup.return_value = 'fake'
        broken.get_backup.return_value = dict(site_url='https://example.com',
            resource_id=10, content='tampered', content_hash='0'*64)
        with self.assertRaises(RuntimeError):
            OfflinePreflight(self.store, broken).prepare(self.approval, **self.kw)
        self.assertFalse(self.preflight.prepare(self.approval, **self.kw)['changes_applied'])

    def test_expired_approval_rejected(self):
        with self.assertRaises(PermissionError):
            self.preflight.prepare(self.approval, **(self.kw | {'now': 1300}))


if __name__ == '__main__':
    unittest.main()
