import unittest
from dataclasses import replace
from unittest.mock import patch
from wordpress_capability_evidence import (CapabilityEvidence,
    CapabilityEvidenceError, validate_capability_evidence)


class CapabilityEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.evidence = CapabilityEvidence(7, 'https://example.com', 12, 'post', True)
        self.target = dict(site_url='https://example.com', user_id=7,
                           resource_id=12, resource_type='post')

    def check(self, evidence=None, **target):
        return validate_capability_evidence(
            self.evidence if evidence is None else evidence,
            **(self.target | target))

    def test_matching_evidence_remains_offline(self):
        self.assertEqual(self.check()['remote_write_authorized'], False)

    def test_missing_evidence(self):
        with self.assertRaises(CapabilityEvidenceError):
            self.check(object())

    def test_wrong_user(self):
        with self.assertRaises(CapabilityEvidenceError):
            self.check(user_id=8)

    def test_wrong_site(self):
        with self.assertRaises(CapabilityEvidenceError):
            self.check(site_url='https://other.example')

    def test_wrong_resource(self):
        with self.assertRaises(CapabilityEvidenceError):
            self.check(resource_id=13)

    def test_wrong_resource_type(self):
        with self.assertRaises(CapabilityEvidenceError):
            self.check(resource_type='page')

    def test_denied_edit(self):
        with self.assertRaises(CapabilityEvidenceError):
            self.check(replace(self.evidence, can_edit=False))

    def test_bool_ids_rejected(self):
        for key in ('user_id', 'resource_id'):
            with self.subTest(key=key), self.assertRaises(CapabilityEvidenceError):
                self.check(**{key: True})

    def test_unsupported_resource_type(self):
        with self.assertRaises(CapabilityEvidenceError):
            self.check(resource_type='media')

    def test_no_network(self):
        with patch('socket.create_connection') as connect:
            self.check()
            connect.assert_not_called()


if __name__ == '__main__':
    unittest.main()
