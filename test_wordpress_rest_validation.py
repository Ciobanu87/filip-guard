import json
import unittest
from wordpress_secure_https import ValidatedHTTPResponse
from wordpress_rest_validation import validate_wordpress_response, InvalidWordPressResponse


def response(data, *, status=200, content_type="application/json; charset=UTF-8"):
    return ValidatedHTTPResponse(status, (("content-type", content_type),), json.dumps(data).encode())


class WordPressRestValidationTests(unittest.TestCase):
    def test_verify(self):
        self.assertEqual(validate_wordpress_response(response({"id": 4, "slug": "editor"}), "verify")["id"], 4)
    def test_posts_pages(self):
        item = {"id": 8, "status": "publish", "link": "https://example.org/article"}
        for kind in ("posts", "pages"):
            self.assertEqual(validate_wordpress_response(response([item]), kind), [item])
            self.assertEqual(validate_wordpress_response(response([]), kind), [])
    def test_reject_bad_http_and_type(self):
        for obj in (response({}, status=401), response({}, content_type="text/html"),
                    ValidatedHTTPResponse(200, (), b"{}"),
                    ValidatedHTTPResponse(200, (("content-type", "application/json"),)*2, b"{}")):
            with self.assertRaises(InvalidWordPressResponse):
                validate_wordpress_response(obj, "verify")
    def test_reject_invalid_json(self):
        for body in (b"", b"{", b"\xff", b"null"):
            with self.assertRaises(InvalidWordPressResponse):
                validate_wordpress_response(ValidatedHTTPResponse(200, (("content-type", "application/json"),), body), "verify")
    def test_reject_bad_user(self):
        for item in ({"id": True, "slug": "x"}, {"id": 0, "slug": "x"}, {"id": 1, "slug": ""}, []):
            with self.assertRaises(InvalidWordPressResponse):
                validate_wordpress_response(response(item), "verify")
    def test_reject_bad_collection(self):
        for item in ({"id": 1}, [{"id": 1, "status": "draft", "link": "https://example.org"}],
                     [{"id": 1, "status": "publish", "link": "http://example.org"}],
                     [{"id": True, "status": "publish", "link": "https://example.org"}],
                     [{"id": 1, "status": "publish", "link": "https://example.org"}]*2):
            with self.assertRaises(InvalidWordPressResponse):
                validate_wordpress_response(response(item), "posts")
    def test_reject_unknown_resource(self):
        with self.assertRaises(InvalidWordPressResponse):
            validate_wordpress_response(response({}), "settings")

if __name__ == "__main__":
    unittest.main()
