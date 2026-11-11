
import os
import tempfile
import unittest
from unittest.mock import Mock

from backup import BackupManager
from rollback import RollbackManager


class TestRollbackManager(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        path = os.path.join(
            self.temp.name, "backups.db"
        )
        self.backups = BackupManager(path)
        self.rollback = RollbackManager(self.backups)
        self.site = "https://example.com"
        self.original = "<p>Original content</p>"

        self.backup_id = self.backups.create_backup(
            self.site, 10, self.original
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_valid_rollback_preparation(self):
        result = self.rollback.prepare_rollback(
            self.backup_id, self.site, 10
        )
        self.assertTrue(result["ready_for_review"])
        self.assertFalse(result["changes_applied"])
        self.assertEqual(
            result["original_content"],
            self.original,
        )

    def test_reject_missing_backup(self):
        with self.assertRaises(ValueError):
            self.rollback.prepare_rollback(
                "nonexistent", self.site, 10
            )

    def test_reject_different_website(self):
        with self.assertRaises(PermissionError):
            self.rollback.prepare_rollback(
                self.backup_id,
                "https://other.com",
                10,
            )

    def test_reject_different_resource(self):
        with self.assertRaises(PermissionError):
            self.rollback.prepare_rollback(
                self.backup_id, self.site, 99
            )

    def test_reject_invalid_backup_id(self):
        with self.assertRaises(ValueError):
            self.rollback.prepare_rollback(
                "", self.site, 10
            )

    def test_reject_corrupted_backup(self):
        fake_backups = Mock()
        fake_backups.get_backup.return_value = {
            "site_url": self.site,
            "resource_id": 10,
            "content": "Modified content",
            "content_hash": "0" * 64,
        }

        rollback = RollbackManager(fake_backups)

        with self.assertRaises(ValueError):
            rollback.prepare_rollback(
                self.backup_id, self.site, 10
            )


if __name__ == "__main__":
    unittest.main()
