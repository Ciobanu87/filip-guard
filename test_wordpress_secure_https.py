
import socket
import unittest
from unittest.mock import patch

from wordpress_secure_https import (
    UnsafeDestinationError,
    create_verified_connection,
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


    def test_https_uses_verified_ip(self):
        with patch(
            "wordpress_secure_https.resolve_public_ips",
            return_value=["8.8.8.8"],
        ), patch(
            "wordpress_secure_https.socket.create_connection"
        ) as connect, patch(
            "ssl.create_default_context"
        ) as ssl_context:
            result = create_verified_connection("example.com")

            connect.assert_called_once_with(
                ("8.8.8.8", 443),
                timeout=15,
            )
            ssl_context.return_value.wrap_socket.assert_called_once_with(
                connect.return_value,
                server_hostname="example.com",
            )
            self.assertIs(
                result,
                ssl_context.return_value.wrap_socket.return_value,
            )

    def test_https_rejects_unsafe_dns(self):
        with patch(
            "wordpress_secure_https.resolve_public_ips",
            side_effect=UnsafeDestinationError("Blocked"),
        ), patch(
            "wordpress_secure_https.socket.create_connection"
        ) as connect:
            with self.assertRaises(UnsafeDestinationError):
                create_verified_connection("example.com")

            connect.assert_not_called()


    def test_https_closes_socket_on_tls_failure(self):
        import ssl

        with patch(
            "wordpress_secure_https.resolve_public_ips",
            return_value=["8.8.8.8"],
        ), patch(
            "wordpress_secure_https.socket.create_connection"
        ) as connect, patch(
            "ssl.create_default_context"
        ) as ssl_context:
            ssl_context.return_value.wrap_socket.side_effect = (
                ssl.SSLError("TLS failed")
            )

            with self.assertRaises(ConnectionError):
                create_verified_connection("example.com")

            connect.return_value.close.assert_called_once()


    def test_secure_https_get_success(self):
        from wordpress_secure_https import secure_https_get

        with patch(
            "wordpress_secure_https.create_verified_connection"
        ) as connect:
            connection = connect.return_value
            connection.recv.side_effect = [
                b"HTTP/1.1 200 OK\r\n\r\nHello",
                b"",
            ]

            result = secure_https_get(
                "example.com", "/wp-json/"
            )

            self.assertEqual(
                result,
                b"HTTP/1.1 200 OK\r\n\r\nHello",
            )
            connection.sendall.assert_called_once()
            connection.close.assert_called_once()

    def test_secure_https_get_rejects_large_response(self):
        from wordpress_secure_https import secure_https_get

        with patch(
            "wordpress_secure_https.create_verified_connection"
        ) as connect:
            connection = connect.return_value

            connection.recv.side_effect = [
                b"A" * (2 * 1024 * 1024 + 1),
            ]

            with self.assertRaisesRegex(
                ValueError, "HTTPS response too large"
            ):
                secure_https_get("example.com", "/wp-json/")

            connection.close.assert_called_once()



if __name__ == "__main__":
    unittest.main()
