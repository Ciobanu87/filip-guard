import json
import unittest
from wordpress_secure_https import ValidatedHTTPResponse
from wordpress_rest_validation import validate_wordpress_response, InvalidWordPressResponse


def response(body):
    if isinstance(body, (dict, list)):
        body = json.dumps(body).encode()
    return ValidatedHTTPResponse(200, (('content-type', 'application/json'),), body)


class RestValidationHardeningTests(unittest.TestCase):
    def test_safe_links(self):
        for url in ('https://example.org/p', 'https://sub.example.org:443/p?q=1'):
            self.assertEqual(validate_wordpress_response(response([{'id': 1, 'status': 'publish', 'link': url}]), 'posts')[0]['link'], url)

    def test_unsafe_links(self):
        urls = ('https://localhost/x', 'https://127.0.0.1/x', 'https://10.0.0.1/x',
                'https://user:pass@example.org/x', 'https://example.org:8080/x',
                'https://example.org/#fragment', 'https://example.org/\nInjected',
                'https://example.org\\@evil.org/', 'https://example.org/x y',
                'https://[::1]/x', 'http://example.org/x', 'https://example.org.evil.org:444/x')
        for url in urls:
            with self.subTest(url=url), self.assertRaises(InvalidWordPressResponse):
                validate_wordpress_response(response([{'id': 1, 'status': 'publish', 'link': url}]), 'pages')

    def test_duplicate_json_keys(self):
        for raw in (b'{"id":1,"id":2,"slug":"editor"}',
                    b'[{"id":1,"status":"publish","link":"https://example.org/","link":"https://evil.org/"}]'):
            with self.subTest(raw=raw), self.assertRaises(InvalidWordPressResponse):
                validate_wordpress_response(response(raw), 'verify' if raw.startswith(b'{') else 'posts')

    def test_invalid_slug(self):
        with self.assertRaises(InvalidWordPressResponse):
            validate_wordpress_response(response({'id': 1, 'slug': 'editor\nadmin'}), 'verify')

    def test_nonfinite_json(self):
        with self.assertRaises(InvalidWordPressResponse):
            validate_wordpress_response(response(b'{"id":1,"slug":"x","other":NaN}'), 'verify')


if __name__ == '__main__':
    unittest.main()
