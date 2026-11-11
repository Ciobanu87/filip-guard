"""FILIP GUARD - WordPress repair workflow.

Read-only preparation. Never modifies a WordPress site.
"""

from wordpress_connection import WordPressConnection
from repair_coordinator import RepairCoordinator


class WordPressRepairWorkflow:
    def __init__(self, backup_manager):
        self.connection = WordPressConnection()
        self.coordinator = RepairCoordinator(backup_manager)

    def verify_site(self, site_url, username, app_password):
        """Verify WordPress access without changing content."""
        return self.connection.verify(
            site_url, username, app_password
        )

    def prepare_change(
        self,
        approval,
        site_url,
        resource_id,
        original_content,
        proposed_content,
    ):
        """Prepare an approved change for review only."""
        result = self.coordinator.prepare_change(
            approval,
            site_url,
            resource_id,
            original_content,
            proposed_content,
        )

        if result.get("changes_applied") is not False:
            raise RuntimeError(
                "Unsafe workflow result: changes must not be applied."
            )

        return result

    def prepare_restore(self, backup_id, site_url, resource_id):
        """Prepare original content for review only."""
        result = self.coordinator.prepare_restore(
            backup_id, site_url, resource_id
        )

        if result.get("changes_applied") is not False:
            raise RuntimeError(
                "Unsafe workflow result: restore must remain read-only."
            )

        return result
