"""Offline UI checks: never contact a website."""
import unittest
from unittest.mock import Mock, patch
from wordpress_public_audit_ui import _hostname_from_scan, render_public_wordpress_audit


class PublicAuditUITests(unittest.TestCase):
    def setUp(self):
        self.rows = [{'page': 'https://example.org/a', 'http_status': 200}]
        self.st = Mock()

    @patch('wordpress_public_audit_ui.build_public_wordpress_audit')
    def test_no_click_means_no_network(self, audit):
        self.st.button.return_value = False
        self.assertIsNone(render_public_wordpress_audit(self.rows, 'https://example.org', st_module=self.st))
        audit.assert_not_called()

    @patch('wordpress_public_audit_ui.build_public_wordpress_audit')
    def test_explicit_click_builds_readonly_report(self, audit):
        self.st.button.return_value = True
        report = {'inventory_coverage': {'inventory_count': 1, 'not_scanned_count': 0, 'not_scanned': []},
                  'incomplete_scans': [], 'seo_recommendations': [], 'autofix': False}
        audit.return_value = report
        self.assertIs(render_public_wordpress_audit(self.rows, 'https://example.org', st_module=self.st), report)
        audit.assert_called_once_with('example.org', self.rows, per_page=20, timeout=15)

    @patch('wordpress_public_audit_ui.build_public_wordpress_audit')
    def test_reject_other_site_without_network(self, audit):
        self.st.button.return_value = True
        self.assertIsNone(render_public_wordpress_audit(self.rows, 'https://other.org', st_module=self.st))
        audit.assert_not_called()
        self.st.warning.assert_called_once()

    @patch('wordpress_public_audit_ui.build_public_wordpress_audit')
    def test_failure_is_visible(self, audit):
        self.st.button.return_value = True
        audit.side_effect = ValueError('REST endpoint unavailable')
        self.assertIsNone(render_public_wordpress_audit(self.rows, 'https://example.org', st_module=self.st))
        self.st.warning.assert_called_once()

    def test_invalid_contexts(self):
        for url in ('http://example.org', 'https://user@example.org',
                    'https://example.org:8443', 'https://example.org/post',
                    'https://example.org/?token=secret',
                    'https://example.org/#fragment'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                _hostname_from_scan(url, self.rows)
        with self.assertRaises(ValueError):
            _hostname_from_scan('https://example.org', [])


if __name__ == '__main__':
    unittest.main()
