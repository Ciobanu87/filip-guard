"""Offline inventory tests; all WordPress network requests are mocked."""
import unittest
from unittest.mock import patch, call

from wordpress_public_inventory import collect_public_inventory, PublicInventoryError


class PublicInventoryTests(unittest.TestCase):
    @patch("wordpress_public_inventory.fetch_public_wordpress")
    def test_collect_posts_and_pages(self, fetch):
        fetch.side_effect = [
            [{"id": 1, "status": "publish", "link": "https://example.org/a"}],
            [{"id": 1, "status": "publish", "link": "https://example.org/b"}],
        ]
        self.assertEqual(collect_public_inventory("example.org", per_page=5), [
            {"resource": "posts", "id": 1, "url": "https://example.org/a"},
            {"resource": "pages", "id": 1, "url": "https://example.org/b"},
        ])
        self.assertEqual(fetch.call_args_list, [
            call("example.org", "posts", per_page=5, timeout=15),
            call("example.org", "pages", per_page=5, timeout=15),
        ])

    @patch("wordpress_public_inventory.fetch_public_wordpress")
    def test_empty_inventory(self, fetch):
        fetch.return_value = []
        self.assertEqual(collect_public_inventory("example.org"), [])
        self.assertEqual(fetch.call_count, 2)

    @patch("wordpress_public_inventory.fetch_public_wordpress")
    def test_invalid_input_does_not_fetch(self, fetch):
        for size in (0, 101, True, 1.0, "20", None):
            with self.subTest(size=size), self.assertRaises(ValueError):
                collect_public_inventory("example.org", per_page=size)
        for host in ("", "https://example.org", "localhost:443", None):
            with self.subTest(host=host), self.assertRaises(ValueError):
                collect_public_inventory(host)
        for timeout in (0, True, float("inf"), "15"):
            with self.subTest(timeout=timeout), self.assertRaises(ValueError):
                collect_public_inventory("example.org", timeout=timeout)
        fetch.assert_not_called()

    @patch("wordpress_public_inventory.fetch_public_wordpress")
    def test_second_fetch_failure_never_returns_partial_data(self, fetch):
        fetch.side_effect = [[{"id": 1, "status": "publish", "link": "https://example.org/a"}], ValueError("invalid pages")]
        with self.assertRaises(ValueError):
            collect_public_inventory("example.org")

    @patch("wordpress_public_inventory.fetch_public_wordpress")
    def test_reject_oversized_or_malformed_result(self, fetch):
        for result in (None, {}, [{"id": 1, "status": "draft", "link": "https://example.org/a"}],
                       [{"id": True, "status": "publish", "link": "https://example.org/a"}],
                       [{"id": 1, "status": "publish", "link": "http://example.org/a"}]):
            with self.subTest(result=result):
                fetch.side_effect = None
                fetch.return_value = result
                with self.assertRaises(PublicInventoryError):
                    collect_public_inventory("example.org")
        fetch.return_value = [{"id": i + 1, "status": "publish", "link": "https://example.org/a"} for i in range(3)]
        with self.assertRaises(PublicInventoryError):
            collect_public_inventory("example.org", per_page=2)


if __name__ == "__main__":
    unittest.main()
