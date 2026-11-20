"""Integration tests intended to run in FILIP GUARD repository with its real backup.py."""
import os
from sqlite_test_utils import test_db
import tempfile
import unittest

from backup import BackupManager
from wordpress_approval_store import ApprovalStore
from wordpress_offline_preflight import OfflinePreflight


class RealBackupIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.approval_path = os.path.join(self.temp.name, 'approvals.sqlite')
        self.backup_path = os.path.join(self.temp.name, 'backups.sqlite')
        self.approvals = ApprovalStore(self.approval_path)
        self.backups = BackupManager(self.backup_path)
        self.preflight = OfflinePreflight(self.approvals, self.backups)
        self.args = dict(site_url='https://example.com', resource_id=13,
                         user_id=4, current_content='<p>before</p>',
                         proposed_content='<p>after</p>', now=1000)
        self.approval = self.approvals.issue(
            site_url=self.args['site_url'], resource_id=13, user_id=4,
            original_content=self.args['current_content'],
            proposed_content=self.args['proposed_content'],
            trusted_authorization=True, now=1000)

    def test_real_backup_verified_and_persists_after_reopen(self):
        result = self.preflight.prepare(self.approval, **self.args)
        self.assertFalse(result['changes_applied'])
        reopened = BackupManager(self.backup_path)
        self.assertEqual(reopened.get_backup(result['backup_id'])['content'], '<p>before</p>')
        with self.assertRaises(PermissionError):
            OfflinePreflight(ApprovalStore(self.approval_path), reopened).prepare(
                self.approval, **self.args)

    def test_corrupted_real_backup_fails_integrity_check(self):
        backup_id = self.backups.create_backup('https://example.com', 13, '<p>before</p>')
        with test_db(self.backup_path) as db:
            db.execute('UPDATE backups SET content=? WHERE backup_id=?', ('tampered', backup_id))
        with self.assertRaises(ValueError):
            self.backups.get_backup(backup_id)

    def test_failed_backup_does_not_consume_approval(self):
        class FailingBackup:
            def create_backup(self, *args):
                raise OSError('disk unavailable')
        with self.assertRaises(OSError):
            OfflinePreflight(self.approvals, FailingBackup()).prepare(self.approval, **self.args)
        result = self.preflight.prepare(self.approval, **self.args)
        self.assertFalse(result['changes_applied'])

    def test_expired_approval_does_not_create_backup(self):
        with self.assertRaises(PermissionError):
            self.preflight.prepare(self.approval, **(self.args | {'now': 1400}))
        with test_db(self.backup_path) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM backups').fetchone()[0], 0)


if __name__ == '__main__':
    unittest.main()
