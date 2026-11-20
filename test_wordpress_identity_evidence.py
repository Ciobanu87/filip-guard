import json
import unittest
from unittest.mock import patch
from wordpress_identity_evidence import (
    WordPressIdentityError, parse_wordpress_identity
)


class WordPressIdentityTests(unittest.TestCase):
    def payload(self, **changes):
        data = {"id": 42, "slug": "editor", "name": "Editor"}
        data.update(changes)
        return json.dumps(data).encode()

    def test_valid_is_diagnostic_only(self):
        result = parse_wordpress_identity(self.payload())
        self.assertEqual((result.user_id, result.username), (42, "editor"))
        self.assertFalse(result.remote_identity_verified)
        self.assertFalse(result.remote_write_authorized)

    def test_no_network(self):
        with patch("socket.create_connection") as connect:
            parse_wordpress_identity(self.payload())
            connect.assert_not_called()

    def test_invalid_id(self):
        for value in (True, False, 0, -1, "42", None):
            with self.subTest(value=value), self.assertRaises(WordPressIdentityError):
                parse_wordpress_identity(self.payload(id=value))

    def test_invalid_slug(self):
        for value in ("", None, 4, "a\nb", "a" * 129):
            with self.subTest(value=value), self.assertRaises(WordPressIdentityError):
                parse_wordpress_identity(self.payload(slug=value))

    def test_invalid_name(self):
        for value in (None, 4, "a\nb", "a" * 257):
            with self.subTest(value=value), self.assertRaises(WordPressIdentityError):
                parse_wordpress_identity(self.payload(name=value))

    def test_malformed_json(self):
        for value in (b"", b"{", b"[]", b"null", b"true", b'"text"', b"\\xff"):
            with self.subTest(value=value), self.assertRaises(WordPressIdentityError):
                parse_wordpress_identity(value)

    def test_size_limit(self):
        with self.assertRaises(WordPressIdentityError):
            parse_wordpress_identity(b"x" * 65537)

    def test_rejects_text_input(self):
        with self.assertRaises(WordPressIdentityError):
            parse_wordpress_identity('{"id":42}')

    def test_extra_fields_do_not_grant_permission(self):
        result = parse_wordpress_identity(self.payload(capabilities={"administrator": True}))
        self.assertFalse(result.remote_write_authorized)

    def test_missing_required_fields(self):
        for value in (b'{"id":42,"slug":"editor"}', b'{"slug":"editor","name":"Editor"}'):
            with self.assertRaises(WordPressIdentityError):
                parse_wordpress_identity(value)


if __name__ == "__main__":
    unittest.main()
