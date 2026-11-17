import unittest
from unittest.mock import patch
from wordpress_readonly_endpoints import readonly_path, InvalidWordPressEndpoint

class WordPressReadOnlyEndpointTests(unittest.TestCase):
    def test_verify_path(self):
        self.assertEqual(readonly_path("verify"), "/wp-json/wp/v2/users/me")
    def test_posts(self):
        self.assertEqual(readonly_path("posts"), "/wp-json/wp/v2/posts?per_page=20&status=publish&context=view")
    def test_pages(self):
        self.assertEqual(readonly_path("pages", per_page=100), "/wp-json/wp/v2/pages?per_page=100&status=publish&context=view")
    def test_reject_arbitrary_endpoints(self):
        for resource in ("/wp-json/wp/v2/users", "users", "settings", "posts/1", "posts?status=draft",
                         "posts\\r\\nAuthorization: secret", "", None, 1, "POSTS", "https://example.com"):
            with self.subTest(resource=resource), self.assertRaises(InvalidWordPressEndpoint):
                readonly_path(resource)
    def test_reject_page_size_abuse(self):
        for value in (0, 101, -1, True, False, 1.0, "20", None, 100000):
            with self.subTest(value=value), self.assertRaises(InvalidWordPressEndpoint):
                readonly_path("posts", per_page=value)
    def test_no_network_or_credentials(self):
        with patch("socket.create_connection") as connect:
            self.assertEqual(readonly_path("verify"), "/wp-json/wp/v2/users/me")
            connect.assert_not_called()
if __name__ == "__main__": unittest.main()
