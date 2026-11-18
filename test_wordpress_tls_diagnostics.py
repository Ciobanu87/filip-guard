"""Offline diagnostics tests; no live network or WordPress credentials."""
import socket
import ssl
import unittest
from wordpress_tls_diagnostics import classify_tls_failure


class TLSDiagnosticsTests(unittest.TestCase):
    def test_certificate_error_nested(self):
        outer = ConnectionError('Verified TLS connection failed')
        outer.__cause__ = ssl.SSLCertVerificationError('certificate verify failed')
        self.assertEqual(classify_tls_failure(outer)['code'], 'certificate_verification')

    def test_timeout_nested(self):
        outer = ConnectionError('Verified TLS connection failed')
        outer.__cause__ = socket.timeout('timed out')
        self.assertEqual(classify_tls_failure(outer)['code'], 'timeout')

    def test_refused(self):
        outer = ConnectionError('Verified TLS connection failed')
        outer.__cause__ = ConnectionRefusedError('refused')
        self.assertEqual(classify_tls_failure(outer)['code'], 'connection_refused')

    def test_handshake_error(self):
        outer = ConnectionError('Verified TLS connection failed')
        outer.__cause__ = ssl.SSLError('handshake failed')
        self.assertEqual(classify_tls_failure(outer)['code'], 'tls_handshake')

    def test_network_error(self):
        outer = ConnectionError('Verified TLS connection failed')
        outer.__cause__ = OSError('network down')
        self.assertEqual(classify_tls_failure(outer)['code'], 'network_error')

    def test_unknown_is_safe(self):
        result = classify_tls_failure(ConnectionError('secret-host.example:443'))
        self.assertEqual(result['code'], 'unknown')
        self.assertNotIn('secret-host', result['message'])

    def test_cyclic_cause_terminates(self):
        err = ConnectionError('failed')
        err.__cause__ = err
        self.assertEqual(classify_tls_failure(err)['code'], 'unknown')

    def test_no_connection_attempt(self):
        from unittest.mock import patch
        with patch('socket.create_connection', side_effect=AssertionError('network used')):
            classify_tls_failure(ConnectionError('failed'))


if __name__ == '__main__':
    unittest.main()
