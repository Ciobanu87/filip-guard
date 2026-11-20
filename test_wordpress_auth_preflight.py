import unittest
from unittest.mock import patch
from wordpress_auth_preflight import validate_auth_preflight, AuthPreflightError

class AuthPreflightTests(unittest.TestCase):
    def check(self, site='https://example.com', user='editor', password='secret'):
        return validate_auth_preflight(site, user, password)

    def test_valid_is_diagnostic_only(self):
        r = self.check()
        self.assertEqual(r.hostname, 'example.com')
        self.assertFalse(r.remote_identity_verified)
        self.assertFalse(r.remote_write_authorized)
        self.assertNotIn('secret', repr(r))

    def test_default_port(self):
        self.assertEqual(self.check(site='https://example.com:443/').hostname, 'example.com')

    def test_no_network(self):
        with patch('socket.create_connection') as network:
            self.check()
            network.assert_not_called()

    def test_invalid_urls(self):
        for site in ('http://example.com', 'https://example.com:8443',
                     'https://user:pass@example.com', 'https://example.com/post',
                     'https://example.com/?q=1', 'https://example.com/#frag',
                     ' https://example.com', 'https://-bad.example.com',
                     'https://bad..example.com', 'https://example.com:bad'):
            with self.subTest(site=site), self.assertRaises(AuthPreflightError):
                self.check(site=site)

    def test_invalid_username(self):
        for user in ('', ' ', 'bad\nname', 'x'*129, None):
            with self.subTest(user=user), self.assertRaises(AuthPreflightError):
                self.check(user=user)

    def test_invalid_password(self):
        for password in ('', ' ', 'bad\nsecret', 'x'*513, None):
            with self.subTest(password=str(password)[:8]), self.assertRaises(AuthPreflightError):
                self.check(password=password)

    def test_secret_not_in_error(self):
        secret = 'private-secret-123'
        with self.assertRaises(AuthPreflightError) as error:
            self.check(site='http://example.com', password=secret)
        self.assertNotIn(secret, str(error.exception))

if __name__ == '__main__':
    unittest.main()
