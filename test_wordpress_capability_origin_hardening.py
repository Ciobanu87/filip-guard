import unittest
from dataclasses import replace
from wordpress_capability_evidence import (
    CapabilityEvidence, CapabilityEvidenceError, validate_capability_evidence
)

class CapabilityOriginHardeningTests(unittest.TestCase):
    def setUp(self):
        self.e = CapabilityEvidence(4, 'https://example.com', 9, 'post', True)

    def check(self, evidence=None, **kwargs):
        args = dict(site_url='https://example.com', user_id=4,
                    resource_id=9, resource_type='post')
        args.update(kwargs)
        return validate_capability_evidence(evidence or self.e, **args)

    def reject(self, **kwargs):
        with self.assertRaises(CapabilityEvidenceError):
            self.check(**kwargs)

    def test_valid(self):
        self.assertEqual(self.check(), {'offline_capability_check': True, 'remote_write_authorized': False})

    def test_default_port(self):
        self.assertFalse(self.check(site_url='https://example.com:443')['remote_write_authorized'])

    def test_other_port(self):
        self.reject(site_url='https://example.com:8443')

    def test_path(self):
        self.reject(site_url='https://example.com/other')

    def test_query(self):
        self.reject(site_url='https://example.com/?q=1')

    def test_fragment(self):
        self.reject(site_url='https://example.com/#frag')

    def test_credentials(self):
        self.reject(site_url='https://user:pass@example.com')

    def test_whitespace(self):
        self.reject(site_url=' https://example.com')

    def test_invalid_port(self):
        self.reject(site_url='https://example.com:bad')

    def test_invalid_hostname(self):
        self.reject(site_url='https://-bad.example.com')

    def test_evidence_wrong_port(self):
        self.reject(evidence=replace(self.e, site_url='https://example.com:8443'))

    def test_evidence_wrong_resource(self):
        self.reject(evidence=replace(self.e, resource_id=10))

    def test_evidence_no_permission(self):
        self.reject(evidence=replace(self.e, can_edit=False))

    def test_boolean_user_id(self):
        self.reject(user_id=True)

    def test_evidence_wrong_user(self):
        self.reject(evidence=replace(self.e, user_id=5))

if __name__ == '__main__':
    unittest.main()
