
"""Safe repair preparation for FILIP GUARD.

No WordPress changes are performed here.
"""

import hashlib
from urllib.parse import urlparse

from auth import validate_approval


class RepairEngine:
    def __init__(self, backup_manager):
        self.backup_manager = backup_manager

    @staticmethod
    def content_hash(content):
        if not isinstance(content, str):
            raise ValueError("Content must be text.")

        return hashlib.sha256(
            content.encode("utf-8")
        ).hexdigest()

    def prepare_repair(
        self,
        approval,
        site_url,
        resource_id,
        original_content,
        proposed_content,
    ):
        """Check approval and save original content."""

        original_hash = self.content_hash(
            original_content
        )
        proposed_hash = self.content_hash(
            proposed_content
        )

        if original_hash == proposed_hash:
            raise ValueError(
                "No content changes detected."
            )

        if not validate_approval(
            approval,
            site_url,
            resource_id,
            original_hash,
            proposed_hash,
        ):
            raise PermissionError(
                "Repair approval is invalid."
            )

        backup_id = self.backup_manager.create_backup(
            site_url,
            resource_id,
            original_content,
        )

        backup = self.backup_manager.get_backup(
            backup_id
        )

        if backup is None:
            raise RuntimeError(
                "Backup verification failed."
            )

        if (
            backup["site_url"] != site_url
            or backup["resource_id"] != resource_id
            or backup["content_hash"] != original_hash
            or backup["content"] != original_content
        ):
            raise RuntimeError(
                "Backup content does not match."
            )

        return {
            "ready_for_review": True,
            "backup_id": backup_id,
            "original_hash": original_hash,
            "proposed_hash": proposed_hash,
            "changes_applied": False,
        }
