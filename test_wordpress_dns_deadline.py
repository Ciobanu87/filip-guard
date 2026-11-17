import socket
import threading
import unittest
from unittest.mock import patch

from wordpress_dns_deadline import DNSDeadlineExceeded, getaddrinfo_with_deadline


class DNSDeadlineTests(unittest.TestCase):
    def test_success(self):
        with patch("wordpress_dns_deadline.socket.getaddrinfo", return_value=[("ok",)]) as resolver:
            self.assertEqual(getaddrinfo_with_deadline("example.com"), [("ok",)])
            resolver.assert_called_once_with("example.com", 443, type=socket.SOCK_STREAM)

    def test_dns_error_propagates(self):
        with patch("wordpress_dns_deadline.socket.getaddrinfo", side_effect=socket.gaierror("bad")):
            with self.assertRaises(socket.gaierror):
                getaddrinfo_with_deadline("example.com")

    def test_timeout_never_returns_late_result(self):
        gate = threading.Event()
        entered = threading.Event()
        def slow(*args, **kwargs):
            entered.set()
            gate.wait(2)
            return [("late",)]
        try:
            with patch("wordpress_dns_deadline.socket.getaddrinfo", side_effect=slow):
                with self.assertRaises(DNSDeadlineExceeded):
                    getaddrinfo_with_deadline("example.com", timeout=.02)
                self.assertTrue(entered.is_set())
        finally:
            gate.set()

    def test_invalid_timeout(self):
        for value in (0, -1, True, "3", float("nan"), float("inf")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                getaddrinfo_with_deadline("example.com", timeout=value)


if __name__ == "__main__":
    unittest.main()
