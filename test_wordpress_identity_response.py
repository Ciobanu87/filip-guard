import unittest
from unittest.mock import patch
from wordpress_secure_https import ValidatedHTTPResponse
from wordpress_identity_response import inspect_identity_response, IdentityResponseError


class IdentityResponseTests(unittest.TestCase):
    def response(self, status=200, headers=(('content-type', 'application/json; charset=utf-8'),), body=b'{"id":4,"slug":"editor","name":"Editor"}'):
        return ValidatedHTTPResponse(status, headers, body)

    def test_valid_is_diagnostic_only(self):
        result = inspect_identity_response(self.response())
        self.assertEqual((result.user_id, result.username), (4, 'editor'))
        self.assertFalse(result.remote_identity_verified)
        self.assertFalse(result.remote_write_authorized)

    def test_no_network(self):
        with patch('socket.create_connection') as connect:
            inspect_identity_response(self.response())
            connect.assert_not_called()

    def test_reject_non_200(self):
        for status in (201, 204, 301, 401, 403, 404, 500):
            with self.subTest(status=status), self.assertRaises(IdentityResponseError):
                inspect_identity_response(self.response(status=status))

    def test_reject_content_types(self):
        for headers in ((), (('content-type', 'text/html'),), (('content-type', 'application/json'), ('content-type', 'application/json'))):
            with self.subTest(headers=headers), self.assertRaises(IdentityResponseError):
                inspect_identity_response(self.response(headers=headers))

    def test_reject_invalid_body(self):
        for body in (b'', b'{}', b'[]', b'{"id":true,"slug":"editor","name":"Editor"}'):
            with self.subTest(body=body), self.assertRaises(IdentityResponseError):
                inspect_identity_response(self.response(body=body))

    def test_reject_unvalidated_response(self):
        with self.assertRaises(IdentityResponseError):
            inspect_identity_response({'status': 200})

    def test_reject_malformed_headers(self):
        with self.assertRaises(IdentityResponseError):
            inspect_identity_response(self.response(headers=(('content-type',),)))


if __name__ == '__main__':
    unittest.main()
