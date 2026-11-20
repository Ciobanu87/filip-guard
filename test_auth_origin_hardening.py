import unittest
from dataclasses import replace
from auth import RepairApproval, validate_approval

class AuthOriginHardeningTests(unittest.TestCase):
    def setUp(self):
        self.approval = RepairApproval('https://example.com', 7, 'a'*64, 'b'*64, True, True)

    def check(self, approval=None, target='https://example.com'):
        return validate_approval(approval or self.approval, target, 7, 'a'*64, 'b'*64)

    def test_valid(self): self.assertTrue(self.check())
    def test_explicit_default_port(self): self.assertTrue(self.check(target='https://example.com:443'))
    def test_reject_other_port(self): self.assertFalse(self.check(target='https://example.com:8443'))
    def test_reject_path(self): self.assertFalse(self.check(target='https://example.com/other'))
    def test_reject_query(self): self.assertFalse(self.check(target='https://example.com/?x=1'))
    def test_reject_fragment(self): self.assertFalse(self.check(target='https://example.com/#x'))
    def test_reject_credentials(self): self.assertFalse(self.check(target='https://u:p@example.com'))
    def test_reject_invalid_port(self): self.assertFalse(self.check(target='https://example.com:bad'))
    def test_reject_approval_other_port(self): self.assertFalse(self.check(approval=replace(self.approval, site_url='https://example.com:8443')))
    def test_reject_non_hex_hash(self): self.assertFalse(self.check(approval=replace(self.approval, original_hash='z'*64)))
    def test_reject_bool_id(self): self.assertFalse(self.check(approval=replace(self.approval, resource_id=True)))
    def test_reject_whitespace(self): self.assertFalse(self.check(target=' https://example.com'))
    def test_reject_other_scheme(self): self.assertFalse(self.check(target='http://example.com'))
    def test_reject_other_host(self): self.assertFalse(self.check(target='https://example.org'))
    def test_reject_not_authorized(self): self.assertFalse(self.check(approval=replace(self.approval, authorized=False)))
    def test_reject_not_approved(self): self.assertFalse(self.check(approval=replace(self.approval, approved=False)))
