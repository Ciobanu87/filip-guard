
"""FILIP GUARD - Safe repair coordination.

Preparation and review only.
No WordPress modifications are performed.
"""

from repair_engine import RepairEngine
from rollback import RollbackManager


class RepairCoordinator:
    def __init__(self, backup_manager):
        self.engine = RepairEngine(backup_manager)
        self.rollback = RollbackManager(backup_manager)

    def prepare_change(
        self,
        approval,
        site_url,
        resource_id,
        original_content,
        proposed_content,
    ):
        """Prepare an approved change for review."""

        result = self.engine.prepare_repair(
            approval,
            site_url,
            resource_id,
            original_content,
            proposed_content,
        )

        return {
            "status": "prepared_for_review",
            "backup_id": result["backup_id"],
            "original_hash": result["original_hash"],
            "proposed_hash": result["proposed_hash"],
            "changes_applied": False,
        }

    def prepare_restore(
        self,
        backup_id,
        site_url,
        resource_id,
    ):
        """Prepare original content for review."""

        result = self.rollback.prepare_rollback(
            backup_id,
            site_url,
            resource_id,
        )

        return {
            "status": "restore_ready_for_review",
            "backup_id": result["backup_id"],
            "original_content": result["original_content"],
            "changes_applied": False,
        }
