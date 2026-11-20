import unittest
from hashlib import sha256
from dataclasses import replace
from wordpress_execution_gate import VerifiedChange, verify_prewrite


def digest(s):
    return sha256(s.encode()).hexdigest()

class ExecutionGateTests(unittest.TestCase):
    def setUp(self):
        self.a = VerifiedChange('https://example.com', 10, 5, digest('old'),
                                digest('new'), 100, 200, 'approval-1')
        self.kw = dict(site_url='https://example.com', resource_id=10, user_id=5,
                       current_content='old', proposed_content='new', now=150)

    def test_valid_metadata(self):
        self.assertTrue(verify_prewrite(self.a, **self.kw))

    def test_reject_stale_content(self):
        with self.assertRaises(PermissionError):
            verify_prewrite(self.a, **{**self.kw, 'current_content':'changed'})

    def test_reject_changed_proposal(self):
        with self.assertRaises(PermissionError):
            verify_prewrite(self.a, **{**self.kw, 'proposed_content':'evil'})

    def test_reject_wrong_user(self):
        with self.assertRaises(PermissionError):
            verify_prewrite(self.a, **{**self.kw, 'user_id':6})

    def test_reject_wrong_resource(self):
        with self.assertRaises(PermissionError):
            verify_prewrite(self.a, **{**self.kw, 'resource_id':11})

    def test_reject_wrong_site(self):
        with self.assertRaises(PermissionError):
            verify_prewrite(self.a, **{**self.kw, 'site_url':'https://other.com'})

    def test_reject_expired(self):
        with self.assertRaises(PermissionError):
            verify_prewrite(self.a, **{**self.kw, 'now':200})

    def test_reject_long_lived(self):
        with self.assertRaises(PermissionError):
            verify_prewrite(replace(self.a, expires_at=2000), **self.kw)

    def test_reject_missing_approval_id(self):
        with self.assertRaises(PermissionError):
            verify_prewrite(replace(self.a, approval_id=''), **self.kw)

    def test_reject_identical(self):
        with self.assertRaises(ValueError):
            verify_prewrite(self.a, **{**self.kw, 'proposed_content':'old'})

if __name__ == '__main__':
    unittest.main()
