"""Offline regression tests for shared TCP/TLS deadline helper."""
import socket
import ssl
import unittest
from unittest.mock import Mock, patch
from wordpress_https_deadline import Deadline, DeadlineExceeded, connect_pinned_addresses


class DeadlineTests(unittest.TestCase):
    def test_invalid_timeout(self):
        for value in (0, -1, float('inf'), float('nan'), True, '15'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                Deadline(value)

    def test_deadline_expires(self):
        with patch('wordpress_https_deadline.time.monotonic', side_effect=[10, 12]):
            with self.assertRaises(DeadlineExceeded):
                Deadline(1).remaining()

    def test_no_attempt_after_deadline(self):
        with patch('wordpress_https_deadline.time.monotonic', side_effect=[0, 2]), patch('wordpress_https_deadline.socket.create_connection') as connect:
            with self.assertRaises(DeadlineExceeded):
                connect_pinned_addresses('example.com', ['8.8.8.8'], Deadline(1), context=Mock())
            connect.assert_not_called()

    def test_failed_socket_is_closed(self):
        raw = Mock()
        context = Mock()
        context.wrap_socket.side_effect = ssl.SSLError('TLS failed')
        with patch('wordpress_https_deadline.socket.create_connection', return_value=raw):
            with self.assertRaises(ConnectionError):
                connect_pinned_addresses('example.com', ['8.8.8.8'], Deadline(10), context=context)
        raw.close.assert_called_once()

    def test_successful_handshake(self):
        raw = Mock()
        tls = Mock()
        context = Mock()
        context.wrap_socket.return_value = tls
        with patch('wordpress_https_deadline.socket.create_connection', return_value=raw):
            result = connect_pinned_addresses('example.com', ['8.8.8.8'], Deadline(10), context=context)
        self.assertIs(result, tls)
        tls.do_handshake.assert_called_once()
        context.wrap_socket.assert_called_once_with(raw, server_hostname='example.com', suppress_ragged_eofs=False, do_handshake_on_connect=False)

    def test_second_ip_uses_remaining_budget(self):
        calls = []
        def connect(addr, timeout):
            calls.append(timeout)
            if len(calls) == 1:
                raise socket.timeout('first IP stalled')
            return Mock()
        context = Mock()
        with patch('wordpress_https_deadline.socket.create_connection', side_effect=connect):
            connect_pinned_addresses('example.com', ['8.8.8.8', '1.1.1.1'], Deadline(10), context=context)
        self.assertEqual(len(calls), 2)
        self.assertLessEqual(calls[1], calls[0])


if __name__ == '__main__':
    unittest.main()
