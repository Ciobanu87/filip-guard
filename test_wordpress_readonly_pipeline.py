import json
import unittest
from unittest.mock import patch
from wordpress_readonly_pipeline import validate_readonly_exchange


def wire(data, *, content_type=b'application/json', status=b'200 OK'):
    body = json.dumps(data).encode('utf-8')
    return (b'HTTP/1.1 ' + status + b'\r\nContent-Type: ' + content_type
            + b'\r\nContent-Length: ' + str(len(body)).encode()
            + b'\r\n\r\n' + body)


class OfflinePipelineTests(unittest.TestCase):
    def test_verify(self):
        path, user = validate_readonly_exchange('verify', wire({'id': 2, 'slug': 'editor'}))
        self.assertEqual(path, '/wp-json/wp/v2/users/me')
        self.assertEqual(user['id'], 2)

    def test_posts_pages(self):
        item = {'id': 4, 'status': 'publish', 'link': 'https://example.org/post'}
        for resource in ('posts', 'pages'):
            with self.subTest(resource=resource):
                path, data = validate_readonly_exchange(resource, wire([item]), per_page=3)
                self.assertIn('per_page=3', path)
                self.assertEqual(data, [item])

    def test_disallow_other_paths(self):
        for resource in ('settings', '/wp-json/wp/v2/users', 'posts/4', 'POST', None):
            with self.subTest(resource=resource), self.assertRaises(ValueError):
                validate_readonly_exchange(resource, wire([]))

    def test_reject_malformed_or_redirected(self):
        for raw in (b'', b'HTTP/1.1 302 Found\r\nLocation: https://evil.org\r\n\r\n',
                    wire([], content_type=b'text/html'), wire({}, status=b'401 Unauthorized'),
                    wire({'id': 1, 'slug': 'x'})[:-1], 'not bytes'):
            with self.subTest(raw=str(raw)[:30]), self.assertRaises(ValueError):
                validate_readonly_exchange('verify', raw)

    def test_does_not_open_network(self):
        with patch('socket.create_connection') as connect:
            validate_readonly_exchange('posts', wire([]))
            connect.assert_not_called()


if __name__ == '__main__':
    unittest.main()
