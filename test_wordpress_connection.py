
import unittest
from unittest.mock import Mock

from wordpress_connection import WordPressConnection


class TestWordPressConnection(unittest.TestCase):

    def setUp(self):
        self.adapter = Mock()
        self.adapter.verify_connection.return_value = {
            "connected": True,
            "user_id": 10,
            "username": "testuser",
        }
        self.adapter_class = Mock(
            return_value=self.adapter
        )
        self.connection = WordPressConnection(
            self.adapter_class
        )

    def test_valid_connection(self):
        result = self.connection.verify(
            "https://example.com",
            "testuser",
            "fake-password",
        )
        self.assertTrue(result["connected"])
        self.assertTrue(result["read_only_check"])
        self.assertEqual(result["user_id"], 10)
        self.adapter.close.assert_called_once()

    def test_reject_http(self):
        with self.assertRaises(ValueError):
            self.connection.verify(
                "http://example.com",
                "testuser",
                "fake-password",
            )

    def test_reject_url_credentials(self):
        with self.assertRaises(ValueError):
            self.connection.verify(
                "https://user:pass@example.com",
                "testuser",
                "fake-password",
            )

    def test_reject_missing_username(self):
        with self.assertRaises(ValueError):
            self.connection.verify(
                "https://example.com",
                "",
                "fake-password",
            )

    def test_reject_missing_password(self):
        with self.assertRaises(ValueError):
            self.connection.verify(
                "https://example.com",
                "testuser",
                "",
            )

    def test_reject_failed_verification(self):
        self.adapter.verify_connection.return_value = {
            "connected": False,
            "user_id": None,
        }

        with self.assertRaises(ConnectionError):
            self.connection.verify(
                "https://example.com",
                "testuser",
                "fake-password",
            )

        self.adapter.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
