"""Mocked tests: never open a real network connection."""
import json
import unittest
from unittest.mock import patch

from wordpress_public_readonly import fetch_public_wordpress


def wire(items):
    body = json.dumps(items).encode('utf-8')
    return (b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n'
            + b'Content-Length: ' + str(len(body)).encode('ascii')
            + b'\r\n\r\n' + body)


class PublicReadOnlyTests(unittest.TestCase):
    @patch('wordpress_public_readonly.secure_https_get')
    def test_posts_and_pages(self, get):
        item = {'id': 3, 'status': 'publish', 'link': 'https://example.org/article'}
        get.return_value = wire([item])
        for kind in ('posts', 'pages'):
            with self.subTest(kind=kind):
                self.assertEqual(fetch_public_wordpress('example.org', kind, per_page=5), [item])
                self.assertEqual(get.call_args.args[0], 'example.org')
                self.assertIn('/wp-json/wp/v2/' + kind, get.call_args.args[1])
                self.assertIn('status=publish', get.call_args.args[1])

    @patch('wordpress_public_readonly.secure_https_get')
    def test_reject_unsupported_resource_before_network(self, get):
        for resource in ('verify', 'users', 'settings', 'posts/1', None, 2, ['posts']):
            with self.subTest(resource=resource), self.assertRaises(ValueError):
                fetch_public_wordpress('example.org', resource)
        get.assert_not_called()

    @patch('wordpress_public_readonly.secure_https_get')
    def test_reject_bad_hostname_before_network(self, get):
        for hostname in ('https://example.org', 'localhost:443', 'bad host', '', None):
            with self.subTest(hostname=hostname), self.assertRaises(ValueError):
                fetch_public_wordpress(hostname, 'posts')
        get.assert_not_called()

    @patch('wordpress_public_readonly.secure_https_get')
    def test_reject_invalid_page_size_before_network(self, get):
        for per_page in (0, 101, True, '20', None):
            with self.subTest(per_page=per_page), self.assertRaises(ValueError):
                fetch_public_wordpress('example.org', 'posts', per_page=per_page)
        get.assert_not_called()

    @patch('wordpress_public_readonly.secure_https_get')
    def test_reject_nonpublished_content(self, get):
        get.return_value = wire([{'id': 1, 'status': 'draft', 'link': 'https://example.org/p'}])
        with self.assertRaises(ValueError):
            fetch_public_wordpress('example.org', 'posts')

    @patch('wordpress_public_readonly.secure_https_get')
    def test_reject_redirect(self, get):
        get.return_value = b'HTTP/1.1 302 Found\r\nLocation: https://example.org/\r\n\r\n'
        with self.assertRaises(ValueError):
            fetch_public_wordpress('example.org', 'pages')

    @patch('wordpress_public_readonly.secure_https_get')
    def test_reject_invalid_timeout_before_network(self, get):
        for timeout in (0, -1, True, '15'):
            with self.subTest(timeout=timeout), self.assertRaises(ValueError):
                fetch_public_wordpress('example.org', 'pages', timeout=timeout)
        get.assert_not_called()


if __name__ == '__main__':
    unittest.main()
