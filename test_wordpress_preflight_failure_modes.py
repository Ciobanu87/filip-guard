"""Offline preflight failure-mode tests; no WordPress networking."""
import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from backup import BackupManager
from wordpress_approval_store import ApprovalStore
from wordpress_offline_preflight import OfflinePreflight


class PreflightFailureModeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.backups = BackupManager(os.path.join(self.tmp.name, 'backups.sqlite'))
        self.approvals = ApprovalStore(os.path.join(self.tmp.name, 'approvals.sqlite'))
        self.gate = OfflinePreflight(self.approvals, self.backups)
        self.params = dict(site_url='https://example.com', resource_id=7,
                           user_id=9, current_content='old', proposed_content='new', now=101, session_id='a' * 43)
        self.approval = self.approvals.issue(site_url='https://example.com',
            resource_id=7, user_id=9, original_content='old', proposed_content='new',
            trusted_authorization=True, now=100, session_id='a' * 43)

    def test_failed_backup_write_does_not_consume_approval(self):
        with patch.object(self.backups, 'create_backup', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                self.gate.prepare(self.approval, **self.params)
        result = self.gate.prepare(self.approval, **self.params)
        self.assertFalse(result['changes_applied'])

    def test_corrupt_backup_read_does_not_consume_approval(self):
        original_get = self.backups.get_backup
        with patch.object(self.backups, 'get_backup', return_value={'content': 'wrong'}):
            with self.assertRaises(RuntimeError):
                self.gate.prepare(self.approval, **self.params)
        self.assertIsNotNone(original_get(self.gate.prepare(self.approval, **self.params)['backup_id']))

    def test_concurrent_preflights_only_one_approval_wins(self):
        def attempt(_):
            try:
                return self.gate.prepare(self.approval, **self.params)
            except PermissionError:
                return None
        with ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(attempt, range(6)))
        winners = [r for r in results if r]
        self.assertEqual(len(winners), 1)
        self.assertFalse(winners[0]['changes_applied'])

    def test_no_wordpress_socket_on_preflight(self):
        with patch('socket.create_connection') as network:
            self.gate.prepare(self.approval, **self.params)
            network.assert_not_called()

    def test_stale_content_rejected_without_backup(self):
        with patch.object(self.backups, 'create_backup') as create:
            with self.assertRaises(PermissionError):
                self.gate.prepare(self.approval, **{**self.params, 'current_content':'changed'})
            create.assert_not_called()

if __name__ == '__main__':
    unittest.main()
