
"""Safe rollback preparation for FILIP GUARD.

This module reads and verifies a saved backup.
It does not modify WordPress websites.
"""

import hashlib
from hmac import compare_digest


class RollbackManager:
    def __init__(self, backup_manager):
        self.backup_manager = backup_manager

    def prepare_rollback(
        self,
        backup_id,
        site_url,
        resource_id,
    ):
        """Retrieve and verify original content."""

        if not isinstance(backup_id, str) or not backup_id:
            raise ValueError("Invalid backup ID.")

        if not isinstance(site_url, str) or not site_url:
            raise ValueError("Invalid site URL.")

        if type(resource_id) is not int or resource_id <= 0:
            raise ValueError("Invalid resource ID.")

        backup = self.backup_manager.get_backup(
            backup_id
        )

        if backup is None:
            raise ValueError("Backup not found.")

        if (
            backup["site_url"] != site_url
            or backup["resource_id"] != resource_id
        ):
            raise PermissionError(
                "Backup does not match the requested resource."
            )

        content = backup["content"]

        if not isinstance(content, str):
            raise ValueError("Invalid backup content.")

        actual_hash = hashlib.sha256(
            content.encode("utf-8")
        ).hexdigest()

        if not compare_digest(
            actual_hash,
            backup["content_hash"],
        ):
            raise ValueError(
                "Backup integrity verification failed."
            )

        return {
            "ready_for_review": True,
            "backup_id": backup_id,
            "site_url": site_url,
            "resource_id": resource_id,
            "original_content": content,
            "changes_applied": False,
        }
