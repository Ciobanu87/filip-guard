
import os
import tempfile
import unittest

from auth import RepairApproval
from backup import BackupManager
from repair_coordinator import RepairCoordinator
from repair_engine import RepairEngine


class TestRepairCoordinator(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        path = os.path.join(self.temp.name, "backups.db")

        self.backups = BackupManager(path)
        self.coordinator = RepairCoordinator(self.backups)

        self.site = "https://example.com"
        self.original = "<p>Original</p>"
        self.proposed = "<p>Updated</p>"

        self.engine = RepairEngine(self.backups)

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
        return self.coordinator.prepare_change(
            approval,
            self.site,
            10,
            self.original,
            self.proposed,
        )

    def test_prepare_change(self):
        result = self.prepare(self.approval())

        self.assertEqual(
            result["status"], "prepared_for_review"
        )
        self.assertFalse(result["changes_applied"])

    def test_backup_created(self):
        result = self.prepare(self.approval())

        backup = self.backups.get_backup(
            result["backup_id"]
        )
        self.assertEqual(
            backup["content"], self.original
        )

    def test_prepare_restore(self):
        result = self.prepare(self.approval())

        restored = self.coordinator.prepare_restore(
            result["backup_id"],
            self.site,
            10,
        )

        self.assertEqual(
            restored["original_content"],
            self.original,
        )
        self.assertFalse(restored["changes_applied"])

    def test_reject_missing_approval(self):
        with self.assertRaises(PermissionError):
            self.prepare(
                self.approval(approved=False)
            )

    def test_reject_wrong_resource_restore(self):
        result = self.prepare(self.approval())

        with self.assertRaises(PermissionError):
            self.coordinator.prepare_restore(
                result["backup_id"],
                self.site,
                99,
            )

    def test_reject_missing_backup_restore(self):
        with self.assertRaises(ValueError):
            self.coordinator.prepare_restore(
                "missing-backup",
                self.site,
                10,
            )


if __name__ == "__main__":
    unittest.main()
