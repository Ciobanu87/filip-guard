import unittest
from unittest.mock import Mock, patch
from wordpress_secure_https import secure_https_get

class HeaderIntegrationTests(unittest.TestCase):
    def test_safe_header_on_wire(self):
        conn = Mock()
        conn.recv.side_effect = [b'HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\n{}', b'']
        with patch('wordpress_secure_https.create_verified_connection', return_value=conn):
            secure_https_get('example.com', '/wp-json/', headers=(('User-Agent', 'FilipGuard-Test'),))
        self.assertIn(b'User-Agent: FilipGuard-Test\r\n', conn.sendall.call_args.args[0])
        conn.close.assert_called_once()

    def test_unsafe_headers_never_connect(self):
        for headers in ((('Authorization','Basic secret'),), (('Host','evil.com'),), (('User-Agent','ok\r\nX: injected'),)):
            with self.subTest(headers=headers), patch('wordpress_secure_https.create_verified_connection') as connect:
                with self.assertRaises(ValueError):
                    secure_https_get('example.com', headers=headers)
                connect.assert_not_called()

    def test_default_wire_format_unchanged(self):
        conn = Mock()
        conn.recv.side_effect = [b'HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n', b'']
        with patch('wordpress_secure_https.create_verified_connection', return_value=conn):
            secure_https_get('example.com')
        self.assertEqual(conn.sendall.call_args.args[0], b'GET / HTTP/1.1\r\nHost: example.com\r\nAccept: application/json\r\nAccept-Encoding: identity\r\nConnection: close\r\n\r\n')

if __name__ == '__main__':
    unittest.main()
