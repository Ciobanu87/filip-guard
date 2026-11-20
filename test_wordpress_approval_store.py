import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from wordpress_approval_store import ApprovalStore

class ApprovalStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, 'approvals.sqlite')
        self.store = ApprovalStore(self.path)
        self.kw = dict(site_url='https://example.com', resource_id=10,
                       user_id=5, original_content='old', proposed_content='new',
                       trusted_authorization=True, now=100)
        self.review = dict(site_url='https://example.com', resource_id=10,
                           user_id=5, current_content='old', proposed_content='new', now=101)
    def tearDown(self):
        self.tmp.cleanup()
    def issue(self):
        return self.store.issue(**self.kw)
    def test_issuance_requires_trusted_boundary(self):
        with self.assertRaises(PermissionError):
            self.store.issue(**{**self.kw, 'trusted_authorization':False})
    def test_valid_single_use(self):
        a = self.issue()
        self.assertFalse(self.store.consume_for_offline_review(a, **self.review)['changes_applied'])
        with self.assertRaises(PermissionError):
            self.store.consume_for_offline_review(a, **self.review)
    def test_persistent_replay_protection(self):
        a = self.issue()
        self.store.consume_for_offline_review(a, **self.review)
        with self.assertRaises(PermissionError):
            ApprovalStore(self.path).consume_for_offline_review(a, **self.review)
    def test_forged_token_rejected(self):
        a = replace(self.issue(), approval_id='forged')
        with self.assertRaises(PermissionError):
            self.store.consume_for_offline_review(a, **self.review)
    def test_forged_metadata_rejected(self):
        a = replace(self.issue(), expires_at=200)
        with self.assertRaises(PermissionError):
            self.store.consume_for_offline_review(a, **self.review)
    def test_wrong_user_rejected(self):
        with self.assertRaises(PermissionError):
            self.store.consume_for_offline_review(self.issue(), **{**self.review,'user_id':6})
    def test_stale_content_rejected(self):
        with self.assertRaises(PermissionError):
            self.store.consume_for_offline_review(self.issue(), **{**self.review,'current_content':'changed'})
    def test_expiry_rejected(self):
        with self.assertRaises(PermissionError):
            self.store.consume_for_offline_review(self.issue(), **{**self.review,'now':401})
    def test_concurrent_single_winner(self):
        a = self.issue()
        def attempt(_):
            try:
                self.store.consume_for_offline_review(a, **self.review)
                return True
            except PermissionError:
                return False
        with ThreadPoolExecutor(max_workers=8) as pool:
            results=list(pool.map(attempt, range(8)))
        self.assertEqual(sum(results), 1)
    def test_no_network_or_wordpress_calls(self):
        from unittest.mock import patch
        with patch('socket.create_connection') as network:
            a=self.issue()
            self.store.consume_for_offline_review(a, **self.review)
            network.assert_not_called()

if __name__ == '__main__':
    unittest.main()
