import base64
import json
import unittest
from unittest.mock import Mock, patch
from wordpress_authenticated_https import (
    _probe_identity_candidate, WordPressAuthenticationError,
    authenticated_wordpress_get, AuthenticatedTransportDisabled,
)


def wire(status=200, body=None, extra=b''):
    body = json.dumps(body or {'id': 7, 'slug': 'editor', 'name': 'Editor'}).encode()
    return (f'HTTP/1.1 {status} Result\r\nContent-Type: application/json\r\nContent-Length: {len(body)}\r\n'.encode()
            + extra + b'\r\n' + body)


class AuthenticatedCandidateTests(unittest.TestCase):
    def probe(self, response):
        connection = Mock()
        connection.recv.side_effect = [response, b'']
        with patch('wordpress_secure_https.create_verified_connection', return_value=connection) as connect:
            result = _probe_identity_candidate('https://example.com', 'editor', 'abcd efgh')
        connect.assert_called_once_with('example.com', timeout=15)
        connection.close.assert_called_once()
        return result, connection

    def test_identity_with_credentials_only_on_verified_connection(self):
        result, connection = self.probe(wire())
        request = connection.sendall.call_args.args[0]
        self.assertIn(b'GET /wp-json/wp/v2/users/me HTTP/1.1', request)
        self.assertIn(b'Authorization: Basic ' + base64.b64encode(b'editor:abcdefgh'), request)
        self.assertEqual(result['user_id'], 7)
        self.assertFalse(result['remote_write_authorized'])
        self.assertNotIn('abcdefgh', repr(result))

    def test_redirect_auth_denial_partial_and_malformed_response_fail_closed(self):
        for response in (wire(302, extra=b'Location: https://other.example/\r\n'),
                         wire(401), wire(403), wire(206), wire(body={'id': True}), b'broken'):
            with self.subTest(response=response):
                connection = Mock()
                connection.recv.side_effect = [response, b'']
                with patch('wordpress_secure_https.create_verified_connection', return_value=connection) as connect:
                    with self.assertRaises(WordPressAuthenticationError):
                        _probe_identity_candidate('https://example.com', 'editor', 'fictitious-secret')
                connect.assert_called_once()
                connection.close.assert_called_once()

    def test_tls_and_private_dns_failure_send_no_credentials(self):
        for error in (ValueError('private IP'), OSError('TLS failure')):
            with patch('wordpress_secure_https.create_verified_connection', side_effect=error):
                with self.assertRaises(WordPressAuthenticationError) as caught:
                    _probe_identity_candidate('https://example.com', 'editor', 'fictitious-secret')
                self.assertNotIn('fictitious-secret', str(caught.exception))

    def test_socket_failure_closes_and_redacts_exception(self):
        connection = Mock()
        connection.sendall.side_effect = OSError('fictitious-secret')
        with patch('wordpress_secure_https.create_verified_connection', return_value=connection):
            with self.assertRaises(WordPressAuthenticationError) as caught:
                _probe_identity_candidate('https://example.com', 'editor', 'fictitious-secret')
        self.assertNotIn('fictitious-secret', str(caught.exception))
        connection.close.assert_called_once()

    def test_bad_origins_or_injection_do_not_open_connection(self):
        for site, username, password in (
            ('http://example.com', 'editor', 'fake'),
            ('https://example.com@evil.com', 'editor', 'fake'),
            ('https://example.com/path', 'editor', 'fake'),
            ('https://example.com', 'ed:itor', 'fake'),
            ('https://example.com', 'editor', 'fake\r\nX: injected')):
            with patch('wordpress_secure_https.create_verified_connection') as connect:
                with self.assertRaises((ValueError, WordPressAuthenticationError)):
                    _probe_identity_candidate(site, username, password)
                connect.assert_not_called()

    def test_live_entry_cannot_enable_candidate(self):
        with patch('wordpress_secure_https.create_verified_connection') as connect:
            with self.assertRaises(AuthenticatedTransportDisabled):
                authenticated_wordpress_get(enabled=True, site_url='https://example.com')
            connect.assert_not_called()
