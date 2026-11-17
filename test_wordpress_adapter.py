"""Regression tests for disabled legacy authenticated WordPress adapter."""
import unittest
from unittest.mock import patch

from wordpress_adapter import WordPressAdapter


class WordPressAdapterTests(unittest.TestCase):
    def test_rejects_http(self):
        with self.assertRaises(ValueError):
            WordPressAdapter("http://example.com", "user", "password")

    def test_rejects_missing_credentials(self):
        with self.assertRaises(ValueError):
            WordPressAdapter("https://example.com", "", "")

    def test_direct_adapter_cannot_create_authenticated_session(self):
        with patch("wordpress_adapter.requests.Session") as session:
            with self.assertRaisesRegex(RuntimeError, "authentication disabled"):
                WordPressAdapter("https://example.com", "user", "password")
            session.assert_not_called()

    def test_direct_adapter_cannot_contact_wordpress(self):
        with patch("wordpress_adapter.requests.Session") as session:
            with self.assertRaises(RuntimeError):
                WordPressAdapter("https://example.com", "user", "password")
            session.assert_not_called()


if __name__ == "__main__":
    unittest.main()
