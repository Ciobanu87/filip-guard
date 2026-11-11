
import os
import tempfile
import unittest
from unittest.mock import Mock

from auth import RepairApproval
from backup import BackupManager
from repair_engine import RepairEngine


class TestRepairEngine(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        path = os.path.join(self.temp.name, "backups.db")
        self.backups = BackupManager(path)
        self.engine = RepairEngine(self.backups)

        self.site = "https://example.com"
        self.original = "<p>Old content</p>"
        self.proposed = "<p>New content</p>"

    def tearDown(self):
        self.temp.cleanup()

    def approval(self, **changes):
        data = {
            "site_url": self.site,
            "resource_id": 10,
            "original_hash": self.engine.content_hash(
                self.original
            ),
            "proposed_hash": self.engine.content_hash(
                self.proposed
            ),
            "authorized": True,
            "approved": True,
        }
        data.update(changes)
        return RepairApproval(**data)

    def prepare(self, approval):
        return self.engine.prepare_repair(
            approval,
            self.site,
            10,
            self.original,
            self.proposed,
        )

    def test_valid_preparation(self):
        result = self.prepare(self.approval())

        self.assertTrue(result["ready_for_review"])
        self.assertFalse(result["changes_applied"])
        self.assertIsNotNone(
            self.backups.get_backup(result["backup_id"])
        )

    def test_reject_missing_authorization(self):
        with self.assertRaises(PermissionError):
            self.prepare(
                self.approval(authorized=False)
            )

    def test_reject_missing_approval(self):
        with self.assertRaises(PermissionError):
            self.prepare(
                self.approval(approved=False)
            )

    def test_reject_changed_proposal(self):
        with self.assertRaises(PermissionError):
            self.prepare(
                self.approval(proposed_hash="c" * 64)
            )

    def test_reject_identical_content(self):
        with self.assertRaises(ValueError):
            self.engine.prepare_repair(
                self.approval(),
                self.site,
                10,
                self.original,
                self.original,
            )

    def test_reject_invalid_backup(self):
        fake_backups = Mock()
        fake_backups.create_backup.return_value = "fake-id"
        fake_backups.get_backup.return_value = None

        engine = RepairEngine(fake_backups)

        with self.assertRaises(RuntimeError):
            engine.prepare_repair(
                self.approval(),
                self.site,
                10,
                self.original,
                self.proposed,
            )


if __name__ == "__main__":
    unittest.main()
