
import os
import sqlite3
import tempfile
import unittest

from backup import BackupManager


class TestBackupManager(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(
            self.temp.name, "backups.db"
        )
        self.manager = BackupManager(self.db_path)
        self.site = "https://example.com"

    def tearDown(self):
        self.temp.cleanup()

    def test_create_and_restore_content(self):
        backup_id = self.manager.create_backup(
            self.site, 10, "<p>Original</p>"
        )
        saved = self.manager.get_backup(backup_id)

        self.assertEqual(
            saved["content"], "<p>Original</p>"
        )
        self.assertEqual(saved["resource_id"], 10)

    def test_backup_survives_new_manager(self):
        backup_id = self.manager.create_backup(
            self.site, 10, "Important content"
        )

        another_manager = BackupManager(self.db_path)
        saved = another_manager.get_backup(backup_id)

        self.assertEqual(
            saved["content"], "Important content"
        )

    def test_export_recovers_without_original_database(self):
        backup_id = self.manager.create_backup(self.site, 10, 'Recovered ✓')
        destination = os.path.join(self.temp.name, 'recovery.sqlite')
        self.assertEqual(self.manager.export_verified_copy(destination),
                         {'backup_count': 1, 'verified': True})
        os.unlink(self.db_path)
        recovered = BackupManager(destination).get_backup(backup_id)
        self.assertEqual(recovered['content'], 'Recovered ✓')
        self.assertEqual(os.stat(destination).st_mode & 0o777, 0o600)

    def test_export_includes_committed_wal_content(self):
        with sqlite3.connect(self.db_path) as writer:
            writer.execute('PRAGMA journal_mode=WAL')
            backup_id = self.manager.create_backup(self.site, 10, 'WAL content')
            destination = os.path.join(self.temp.name, 'wal-copy.sqlite')
            self.manager.export_verified_copy(destination)
            self.assertEqual(BackupManager(destination).get_backup(backup_id)['content'], 'WAL content')

    def test_export_does_not_overwrite_existing_files(self):
        for destination in (self.db_path, os.path.join(self.temp.name, 'existing')):
            if destination != self.db_path:
                with open(destination, 'w') as file:
                    file.write('keep me')
            with self.assertRaises(FileExistsError):
                self.manager.export_verified_copy(destination)
        with open(destination) as file:
            self.assertEqual(file.read(), 'keep me')

    def test_export_rejects_corrupted_content_and_removes_failed_copy(self):
        backup_id = self.manager.create_backup(self.site, 10, 'Original')
        with sqlite3.connect(self.db_path) as db:
            db.execute('UPDATE backups SET content=? WHERE backup_id=?', ('broken', backup_id))
        destination = os.path.join(self.temp.name, 'bad-copy.sqlite')
        with self.assertRaises(ValueError):
            self.manager.export_verified_copy(destination)
        self.assertFalse(os.path.exists(destination))

    def test_missing_backup(self):
        self.assertIsNone(
            self.manager.get_backup("nonexistent")
        )

    def test_reject_invalid_resource(self):
        with self.assertRaises(ValueError):
            self.manager.create_backup(
                self.site, -1, "Content"
            )

    def test_reject_non_text_content(self):
        with self.assertRaises(ValueError):
            self.manager.create_backup(
                self.site, 10, None
            )

    def test_detect_modified_backup(self):
        backup_id = self.manager.create_backup(
            self.site, 10, "Original"
        )

        with sqlite3.connect(self.db_path) as db:
            db.execute(
                """
                UPDATE backups
                SET content = ?
                WHERE backup_id = ?
                """,
                ("Modified", backup_id),
            )

        with self.assertRaises(ValueError):
            self.manager.get_backup(backup_id)


if __name__ == "__main__":
    unittest.main()
