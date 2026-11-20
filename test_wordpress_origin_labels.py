import unittest
from dataclasses import replace
from auth import RepairApproval, validate_approval
from wordpress_execution_gate import _origin

class OriginLabelTests(unittest.TestCase):
    def setUp(self):
        self.approval = RepairApproval('https://example.com', 1, 'a'*64, 'b'*64, True, True)

    def assert_rejected(self, url):
        with self.assertRaises(ValueError):
            _origin(url)
        self.assertFalse(validate_approval(replace(self.approval, site_url=url), 'https://example.com', 1, 'a'*64, 'b'*64))

    def test_valid_subdomain(self):
        self.assertEqual(_origin('https://my-site.example.com'), 'my-site.example.com')

    def test_default_port(self):
        self.assertEqual(_origin('https://example.com:443'), 'example.com')

    def test_leading_hyphen(self):
        self.assert_rejected('https://-bad.example.com')

    def test_trailing_hyphen(self):
        self.assert_rejected('https://bad-.example.com')

    def test_empty_label(self):
        self.assert_rejected('https://bad..example.com')

    def test_overlong_label(self):
        self.assert_rejected('https://' + 'a'*64 + '.example.com')

    def test_underscore(self):
        self.assert_rejected('https://bad_name.example.com')

    def test_percent_encoded_hostname(self):
        self.assert_rejected('https://%65xample.com')
