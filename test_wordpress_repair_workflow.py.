import unittest
from unittest.mock import MagicMock, patch

from wordpress_repair_workflow import WordPressRepairWorkflow


class TestWordPressRepairWorkflow(unittest.TestCase):

    def setUp(self):
        self.backup_manager = MagicMock()
        self.workflow = WordPressRepairWorkflow(
            self.backup_manager
        )

    def test_verify_site(self):
        with patch.object(
            self.workflow.connection, "verify",
            return_value={"success": True}
        ) as mock_verify:
            result = self.workflow.verify_site(
                "https://example.com",
                "testuser",
                "test-password"
            )

        self.assertEqual(result, {"success": True})
        mock_verify.assert_called_once_with(
            "https://example.com",
            "testuser",
            "test-password"
        )

    def test_prepare_change_read_only(self):
        self.workflow.coordinator.prepare_change = MagicMock(
            return_value={
                "changes_applied": False,
                "backup_id": "backup-123"
            }
        )

        result = self.workflow.prepare_change(
            "approval",
            "https://example.com",
            10,
            "Original",
            "Proposed"
        )

        self.assertFalse(result["changes_applied"])
        self.assertEqual(
            result["backup_id"], "backup-123"
        )

    def test_reject_applied_change(self):
        self.workflow.coordinator.prepare_change = MagicMock(
            return_value={"changes_applied": True}
        )

        with self.assertRaises(RuntimeError):
            self.workflow.prepare_change(
                "approval",
                "https://example.com",
                10,
                "Original",
                "Proposed"
            )

    def test_prepare_restore_read_only(self):
        self.workflow.coordinator.prepare_restore = MagicMock(
            return_value={
                "changes_applied": False,
                "original_content": "Original"
            }
        )

        result = self.workflow.prepare_restore(
            "backup-123",
            "https://example.com",
            10
        )

        self.assertFalse(result["changes_applied"])

    def test_reject_applied_restore(self):
        self.workflow.coordinator.prepare_restore = MagicMock(
            return_value={"changes_applied": True}
        )

        with self.assertRaises(RuntimeError):
            self.workflow.prepare_restore(
                "backup-123",
                "https://example.com",
                10
            )


if __name__ == "__main__":
    unittest.main()
