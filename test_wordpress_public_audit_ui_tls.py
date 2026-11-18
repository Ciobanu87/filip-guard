"""Offline tests for TLS diagnostics displayed by public WordPress audit UI."""
import ssl
import socket
import unittest
from unittest.mock import Mock, patch

from wordpress_public_audit_ui import render_public_wordpress_audit


class AuditTLSUITests(unittest.TestCase):
    def setUp(self):
        self.st = Mock()
        self.st.button.return_value = True
        self.rows = [{'page': 'https://example.org/a', 'http_status': 200}]

    @patch('wordpress_public_audit_ui.build_public_wordpress_audit')
    def test_certificate_message(self, audit):
        outer = ConnectionError('Verified TLS connection failed')
        outer.__cause__ = ssl.SSLCertVerificationError('sensitive-host')
        audit.side_effect = outer
        self.assertIsNone(render_public_wordpress_audit(self.rows, 'https://example.org', st_module=self.st))
        msg = self.st.warning.call_args.args[0]
        self.assertIn('certificate verification', msg)
        self.assertNotIn('sensitive-host', msg)

    @patch('wordpress_public_audit_ui.build_public_wordpress_audit')
    def test_timeout_message(self, audit):
        audit.side_effect = socket.timeout('secret-ip')
        render_public_wordpress_audit(self.rows, 'https://example.org', st_module=self.st)
        msg = self.st.warning.call_args.args[0]
        self.assertIn('timed out', msg)
        self.assertNotIn('secret-ip', msg)

    @patch('wordpress_public_audit_ui.build_public_wordpress_audit')
    def test_validation_message_hides_details(self, audit):
        audit.side_effect = ValueError('secret endpoint details')
        render_public_wordpress_audit(self.rows, 'https://example.org', st_module=self.st)
        msg = self.st.warning.call_args.args[0]
        self.assertIn('could not be validated', msg)
        self.assertNotIn('secret', msg)

    @patch('wordpress_public_audit_ui.build_public_wordpress_audit')
    def test_no_click_no_network(self, audit):
        self.st.button.return_value = False
        render_public_wordpress_audit(self.rows, 'https://example.org', st_module=self.st)
        audit.assert_not_called()

    @patch('wordpress_public_audit_ui.build_public_wordpress_audit')
    def test_success_report(self, audit):
        report = {'inventory_coverage': {'inventory_count': 0, 'not_scanned_count': 0, 'not_scanned': []},
                  'incomplete_scans': [], 'seo_recommendations': [], 'autofix': False}
        audit.return_value = report
        self.assertIs(render_public_wordpress_audit(self.rows, 'https://example.org', st_module=self.st), report)


if __name__ == '__main__':
    unittest.main()
