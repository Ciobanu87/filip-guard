"""Regression tests for the fail-closed WordPress authentication gate."""
import unittest
from unittest.mock import patch

from wordpress_authenticated_https import (
    AuthenticatedTransportDisabled, authenticated_wordpress_get,
)


class AuthenticatedTransportGateTests(unittest.TestCase):
    def test_no_arguments(self):
        with self.assertRaises(AuthenticatedTransportDisabled):
            authenticated_wordpress_get()

    def test_legacy_enabled_flag_cannot_bypass(self):
        with patch('socket.create_connection') as connect:
            with self.assertRaises(AuthenticatedTransportDisabled):
                authenticated_wordpress_get('example.com', 'verify', 'user', 'secret', enabled=True)
            connect.assert_not_called()

    def test_arbitrary_keyword_flags_cannot_bypass(self):
        with self.assertRaises(AuthenticatedTransportDisabled):
            authenticated_wordpress_get(force=True, approved=True, debug=True)

    def test_does_not_echo_credentials(self):
        secret = 'never-print-this-secret'
        with self.assertRaises(AuthenticatedTransportDisabled) as caught:
            authenticated_wordpress_get('example.com', 'verify', 'user', secret)
        self.assertNotIn(secret, str(caught.exception))


if __name__ == '__main__':
    unittest.main()
