
import socket
import unittest
from unittest.mock import patch

from wordpress_secure_https import (
    UnsafeDestinationError,
    resolve_public_ips,
)


def fake_dns(*addresses):
    return [
        (
            socket.AF_INET6 if ":" in ip else socket.AF_INET,
            socket.SOCK_STREAM,
            6,
            "",
            (ip, 443),
        )
        for ip in addresses
    ]


class TestWordPressSecureHTTPS(unittest.TestCase):

    def test_public_ipv4(self):
        with patch(
            "wordpress_secure_https.socket.getaddrinfo",
            return_value=fake_dns("8.8.8.8"),
        ):
            self.assertEqual(
                resolve_public_ips("example.com"),
                ["8.8.8.8"],
            )

    def test_private_ipv4_blocked(self):
        with patch(
            "wordpress_secure_https.socket.getaddrinfo",
            return_value=fake_dns("192.168.1.1"),
        ):
            with self.assertRaises(UnsafeDestinationError):
                resolve_public_ips("example.com")

    def test_loopback_blocked(self):
        with patch(
            "wordpress_secure_https.socket.getaddrinfo",
            return_value=fake_dns("127.0.0.1"),
        ):
            with self.assertRaises(UnsafeDestinationError):
                resolve_public_ips("localhost")

    def test_private_ipv6_blocked(self):
        with patch(
            "wordpress_secure_https.socket.getaddrinfo",
            return_value=fake_dns("fc00::1"),
        ):
            with self.assertRaises(UnsafeDestinationError):
                resolve_public_ips("example.com")

    def test_mixed_addresses_blocked(self):
        with patch(
            "wordpress_secure_https.socket.getaddrinfo",
            return_value=fake_dns(
                "8.8.8.8",
                "10.0.0.1",
            ),
        ):
            with self.assertRaises(UnsafeDestinationError):
                resolve_public_ips("example.com")

    def test_empty_dns_blocked(self):
        with patch(
            "wordpress_secure_https.socket.getaddrinfo",
            return_value=[],
        ):
            with self.assertRaises(UnsafeDestinationError):
                resolve_public_ips("example.com")

    def test_missing_hostname_blocked(self):
        with self.assertRaises(UnsafeDestinationError):
            resolve_public_ips("")


if __name__ == "__main__":
    unittest.main()
