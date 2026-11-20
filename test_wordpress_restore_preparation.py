"""Offline restore review tests using the existing repository rollback contract."""
import os
from sqlite_test_utils import test_db
import tempfile
import unittest

from backup import BackupManager


class RestorePreparationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.directory.name, 'snapshots.sqlite3')
        self.manager = BackupManager(self.db_path)
        self.site = 'https://example.com'
        self.resource = 7
        self.original = '<p>Original page</p>'

    def tearDown(self):
        self.directory.cleanup()

    def rollback(self):
        # Keep production module unmodified; import original when present.
        from rollback import RollbackManager
        return RollbackManager(self.manager)

    def test_restore_preparation_matches_original(self):
        backup_id = self.manager.create_backup(self.site, self.resource, self.original)
        result = self.rollback().prepare_rollback(backup_id, self.site, self.resource)
        self.assertTrue(result['ready_for_review'])
        self.assertEqual(result['original_content'], self.original)
        self.assertFalse(result['changes_applied'])

    def test_cross_site_restore_is_rejected(self):
        backup_id = self.manager.create_backup(self.site, self.resource, self.original)
        with self.assertRaises(PermissionError):
            self.rollback().prepare_rollback(backup_id, 'https://other.example', self.resource)

    def test_cross_resource_restore_is_rejected(self):
        backup_id = self.manager.create_backup(self.site, self.resource, self.original)
        with self.assertRaises(PermissionError):
            self.rollback().prepare_rollback(backup_id, self.site, 8)

    def test_corrupted_backup_cannot_prepare_restore(self):
        backup_id = self.manager.create_backup(self.site, self.resource, self.original)
        with test_db(self.db_path) as db:
            db.execute('UPDATE backups SET content=? WHERE backup_id=?', ('tampered', backup_id))
        with self.assertRaises(ValueError):
            self.rollback().prepare_rollback(backup_id, self.site, self.resource)

    def test_missing_backup_is_rejected(self):
        with self.assertRaises(ValueError):
            self.rollback().prepare_rollback('missing', self.site, self.resource)


if __name__ == '__main__':
    unittest.main()
