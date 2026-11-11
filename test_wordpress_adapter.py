
import unittest
from unittest.mock import Mock, patch

import requests
from wordpress_adapter import WordPressAdapter


class WordPressAdapterTests(unittest.TestCase):

    def test_rejects_http(self):
        with self.assertRaises(ValueError):
            WordPressAdapter(
                "http://example.com", "user", "password"
            )

    def test_rejects_missing_credentials(self):
        with self.assertRaises(ValueError):
            WordPressAdapter(
                "https://example.com", "", ""
            )

    @patch("wordpress_adapter.requests.Session")
    def test_verifies_connection(self, session_class):
        response = Mock()
        response.json.return_value = {
            "id": 12,
            "slug": "editor"
        }
        response.raise_for_status.return_value = None
        session_class.return_value.get.return_value = response

        adapter = WordPressAdapter(
            "https://example.com", "user", "password"
        )
        result = adapter.verify_connection()

        self.assertTrue(result["connected"])
        self.assertEqual(result["user_id"], 12)
        self.assertEqual(result["username"], "editor")

    @patch("wordpress_adapter.requests.Session")
    def test_reads_only_published_posts(self, session_class):
        response = Mock()
        response.json.return_value = []
        response.raise_for_status.return_value = None
        session_class.return_value.get.return_value = response

        adapter = WordPressAdapter(
            "https://example.com", "user", "password"
        )
        adapter.get_posts(200)

        kwargs = session_class.return_value.get.call_args.kwargs
        self.assertEqual(kwargs["params"]["status"], "publish")
        self.assertEqual(kwargs["params"]["per_page"], 100)
        self.assertFalse(kwargs["allow_redirects"])

    @patch("wordpress_adapter.requests.Session")
    def test_connection_error(self, session_class):
        session_class.return_value.get.side_effect = (
            requests.exceptions.Timeout()
        )

        adapter = WordPressAdapter(
            "https://example.com", "user", "password"
        )

        with self.assertRaises(requests.exceptions.Timeout):
            adapter.verify_connection()


if __name__ == "__main__":
    unittest.main()
