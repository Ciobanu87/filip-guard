"""Offline-only AutoFix preflight. No networking and no WordPress writes.

A successful result is NOT permission to execute a remote write: WordPress
capability verification and remote conditional update are still required.
"""
from hashlib import sha256
from hmac import compare_digest


class OfflinePreflight:
    def __init__(self, approval_store, backup_manager):
        self.approvals = approval_store
        self.backups = backup_manager

    def prepare(self, approval, *, site_url, resource_id, user_id,
                current_content, proposed_content, now=None):
        from wordpress_execution_gate import verify_prewrite
        # Validate without consuming before persisting the original snapshot.
        verify_prewrite(approval, site_url=site_url, resource_id=resource_id,
                        user_id=user_id, current_content=current_content,
                        proposed_content=proposed_content, now=now)
        original_hash = sha256(current_content.encode('utf-8')).hexdigest()
        backup_id = self.backups.create_backup(site_url, resource_id, current_content)
        snapshot = self.backups.get_backup(backup_id)
        if not isinstance(snapshot, dict) or (
                snapshot.get('site_url') != site_url
                or snapshot.get('resource_id') != resource_id
                or snapshot.get('content') != current_content
                or not isinstance(snapshot.get('content_hash'), str)
                or not compare_digest(snapshot['content_hash'], original_hash)):
            raise RuntimeError('Verified persistent backup required')
        # Single-use approval is consumed only after a verified backup exists.
        result = self.approvals.consume_for_offline_review(
            approval, site_url=site_url, resource_id=resource_id, user_id=user_id,
            current_content=current_content, proposed_content=proposed_content,
            now=now)
        if result != {'approved_for_offline_review': True, 'changes_applied': False}:
            raise RuntimeError('Unexpected approval result')
        return {'status': 'offline_review_ready', 'backup_id': backup_id,
                'original_hash': original_hash,
                'proposed_hash': sha256(proposed_content.encode('utf-8')).hexdigest(),
                'changes_applied': False}
