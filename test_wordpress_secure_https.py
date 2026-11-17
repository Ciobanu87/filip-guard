
import socket
import ssl
import unittest
from unittest.mock import Mock, patch

from wordpress_secure_https import (
    InvalidHTTPResponse,
    MAX_HEADER_SIZE,
    MAX_RESPONSE_SIZE,
    UnsafeDestinationError,
    parse_http_response,
    secure_https_get,
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

            connect.assert_called_once()
            self.assertEqual(connect.call_args.args[0], ("8.8.8.8", 443))
            self.assertGreater(connect.call_args.kwargs["timeout"], 0)
            self.assertLessEqual(connect.call_args.kwargs["timeout"], 15)
            ssl_context.return_value.wrap_socket.assert_called_once_with(
                connect.return_value,
                server_hostname="example.com",
                suppress_ragged_eofs=False,
                do_handshake_on_connect=False,
            )
            ssl_context.return_value.wrap_socket.return_value.do_handshake.assert_called_once()
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




class TestHTTPResponseValidation(unittest.TestCase):
    def test_content_length_and_case_insensitive_headers(self):
        response = parse_http_response(
            b"HTTP/1.1 200 OK\r\ncOnTeNt-LeNgTh: 5\r\nX-Test: yes\r\n\r\nHello"
        )
        self.assertEqual(response.status, 200)
        self.assertEqual(response.body, b"Hello")
        self.assertIn(("content-length", "5"), response.headers)

    def test_connection_close_framing_and_error_status(self):
        for version in (b"HTTP/1.0", b"HTTP/1.1"):
            with self.subTest(version=version):
                response = parse_http_response(version + b" 404 Not Found\r\n\r\nmissing")
                self.assertEqual(response.status, 404)
                self.assertEqual(response.body, b"missing")

    def test_chunked_decoding(self):
        response = parse_http_response(
            b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n"
            b"4\r\nWiki\r\n5\r\npedia\r\n0\r\n\r\n"
        )
        self.assertEqual(response.body, b"Wikipedia")

    def test_empty_bodies(self):
        for raw in (
            b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n",
            b"HTTP/1.1 204 No Content\r\n\r\n",
            b"HTTP/1.1 205 Reset Content\r\nContent-Length: 0\r\n\r\n",
            b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n0\r\n\r\n",
        ):
            with self.subTest(raw=raw):
                self.assertEqual(parse_http_response(raw).body, b"")

    def test_reject_bad_status_and_header_syntax(self):
        cases = (
            b"", b"not HTTP", b"HTTP/2 200 OK\r\n\r\n",
            b"HTTP/1.1 099 Invalid\r\n\r\n", b"HTTP/1.1 600 Invalid\r\n\r\n",
            b"HTTP/1.1 200\r\n\r\n", b"HTTP/1.1 200 O\x00K\r\n\r\n",
            b"HTTP/1.1 200 OK\nX: a\n\n",
            b"HTTP/1.1 200 OK\r\nX : a\r\n\r\n",
            b"HTTP/1.1 200 OK\r\nX\r\n\r\n",
            b"HTTP/1.1 200 OK\r\nX: a\r\n folded\r\n\r\n",
            b"HTTP/1.1 200 OK\r\nX: a\nb\r\n\r\n",
            b"HTTP/1.1 200 OK\r\nX: a\rb\r\n\r\n",
            b"HTTP/1.1 200 OK\r\nX: a\x00b\r\n\r\n",
            b"HTTP/1.1 200 OK\r\nX: a\x7fb\r\n\r\n",
        )
        for raw in cases:
            with self.subTest(raw=raw):
                with self.assertRaises(InvalidHTTPResponse):
                    parse_http_response(raw)

    def test_reject_ambiguous_or_invalid_framing(self):
        cases = (
            b"Content-Length: 1\r\nContent-Length: 1",  # identical still ambiguous
            b"Content-Length: 1\r\ncontent-length: 2",
            b"Content-Length: 1, 1", b"Content-Length: -1", b"Content-Length: +1",
            b"Content-Length: one", b"Content-Length:",
            b"Content-Length: " + b"9" * 5000,
            b"Content-Length: 1\r\nTransfer-Encoding: chunked",
            b"Transfer-Encoding: chunked\r\nTransfer-Encoding: chunked",
            b"Transfer-Encoding: gzip, chunked", b"Transfer-Encoding: identity",
            b"Content-Encoding: gzip", b"Content-Encoding: identity, gzip",
            b"Trailer: X-Extra", b"Upgrade: websocket",
        )
        for headers in cases:
            with self.subTest(headers=headers[:100]):
                with self.assertRaises(InvalidHTTPResponse):
                    parse_http_response(b"HTTP/1.1 200 OK\r\n" + headers + b"\r\n\r\nx")

    def test_reject_truncated_extra_and_concatenated_data(self):
        for body in (b"", b"abcd", b"abcdef", b"abcdeHTTP/1.1 200 OK\r\n\r\n"):
            with self.subTest(body=body):
                with self.assertRaises(InvalidHTTPResponse):
                    parse_http_response(b"HTTP/1.1 200 OK\r\nContent-Length: 5\r\n\r\n" + body)

    def test_reject_bad_chunks(self):
        for body in (
            b"", b"1", b"1\r\nx", b"1\r\nx!!0\r\n\r\n", b"0\r\n",
            b"0\r\n\r\nextra", b"+1\r\nx\r\n0\r\n\r\n", b"g\r\n",
            b"1;extension=yes\r\nx\r\n0\r\n\r\n",
            b"0\r\nX-Trailer: x\r\n\r\n", b"ffffffffffffffff\r\n",
            b"f" * 9000 + b"\r\n", b"1\nx\n0\n\n",
        ):
            with self.subTest(body=body[:100]):
                with self.assertRaises(InvalidHTTPResponse):
                    parse_http_response(b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n" + body)

    def test_reject_chunked_http10(self):
        with self.assertRaises(InvalidHTTPResponse):
            parse_http_response(b"HTTP/1.0 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n0\r\n\r\n")

    def test_reject_redirects_and_informational_responses(self):
        for code in (100, 101, 103, 301, 302, 304, 307, 308):
            with self.subTest(code=code):
                with self.assertRaises(InvalidHTTPResponse):
                    parse_http_response(
                        f"HTTP/1.1 {code} Status\r\nLocation: https://127.0.0.1/\r\n\r\n".encode()
                    )

    def test_reject_body_on_bodyless_status(self):
        for raw in (
            b"HTTP/1.1 204 No Content\r\n\r\nx",
            b"HTTP/1.1 204 No Content\r\nContent-Length: 0\r\n\r\n",
            b"HTTP/1.1 204 No Content\r\nTransfer-Encoding: chunked\r\n\r\n0\r\n\r\n",
            b"HTTP/1.1 205 Reset Content\r\nContent-Length: 1\r\n\r\nx",
        ):
            with self.subTest(raw=raw):
                with self.assertRaises(InvalidHTTPResponse):
                    parse_http_response(raw)

    def test_response_limits(self):
        prefix = b"HTTP/1.1 200 OK\r\n\r\n"
        at_limit = prefix + b"x" * (MAX_RESPONSE_SIZE - len(prefix))
        self.assertEqual(len(parse_http_response(at_limit).body), MAX_RESPONSE_SIZE - len(prefix))
        for raw in (
            at_limit + b"x",
            b"HTTP/1.1 200 OK\r\nX: " + b"x" * 8192 + b"\r\n\r\n",
            b"HTTP/1.1 200 OK\r\n" + b"X: y\r\n" * 101 + b"\r\n",
            b"HTTP/1.1 200 OK\r\n" + (b"X: " + b"x" * 7000 + b"\r\n") * 10 + b"\r\n",
        ):
            with self.subTest(size=len(raw)):
                with self.assertRaises(InvalidHTTPResponse):
                    parse_http_response(raw)


class TestHTTPSGetValidation(unittest.TestCase):
    def test_invalid_requests_never_connect(self):
        cases = [
            (host, "/", 15) for host in
            (None, "", "example.com\r\nX: y", "user@example.com", "example.com:443",
             "bad host", "https://example.com", "a..com", "example.com..", "-bad.com", "é.com", "2606:4700::1%eth0", "a" * 254)
        ]
        cases += [("example.com", path, 15) for path in
                  (None, "", "https://other.com/", "//other.com/", "/a b", "/\r\nX: y",
                   "/#fragment", "/é", "/\x00", "/\\other", "/" + "x" * 8192)]
        cases += [("example.com", "/", t) for t in (0, -1, float("nan"), float("inf"), True, "15")]
        with patch("wordpress_secure_https.create_verified_connection") as connect:
            for host, path, timeout in cases:
                with self.subTest(host=host, path=path, timeout=timeout):
                    with self.assertRaises(ValueError):
                        secure_https_get(host, path, timeout)
            connect.assert_not_called()

    def test_fragmented_response_and_request(self):
        raw = b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\n{}"
        connection = Mock()
        connection.recv.side_effect = [bytes([c]) for c in raw] + [b""]
        with patch("wordpress_secure_https.create_verified_connection", return_value=connection):
            self.assertEqual(secure_https_get("example.com", "/wp-json/?page=1"), raw)
        connection.sendall.assert_called_once_with(
            b"GET /wp-json/?page=1 HTTP/1.1\r\nHost: example.com\r\n"
            b"Accept: application/json\r\nAccept-Encoding: identity\r\nConnection: close\r\n\r\n"
        )
        connection.close.assert_called_once()

    def test_closes_after_io_errors_and_bad_responses(self):
        for operation, error in (("sendall", OSError("send")),
                                 ("recv", TimeoutError("read")),
                                 ("recv", OSError("read")),
                                 ("recv", ssl.SSLEOFError("abrupt TLS EOF")),
                                 ("settimeout", OSError("timeout"))):
            connection = Mock()
            getattr(connection, operation).side_effect = error
            with self.subTest(operation=operation, error=error):
                with patch("wordpress_secure_https.create_verified_connection", return_value=connection):
                    with self.assertRaises(OSError):
                        secure_https_get("example.com")
                connection.close.assert_called_once()
        for raw in (b"", b"not HTTP", b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nx",
                    b"HTTP/1.1 302 Found\r\nLocation: https://127.0.0.1/\r\n\r\n"):
            connection = Mock()
            connection.recv.side_effect = [raw, b""]
            with self.subTest(raw=raw):
                with patch("wordpress_secure_https.create_verified_connection", return_value=connection) as connect:
                    with self.assertRaises(InvalidHTTPResponse):
                        secure_https_get("example.com")
                    connect.assert_called_once()
                connection.close.assert_called_once()

    def test_oversized_headers_rejected_before_eof(self):
        connection = Mock()
        connection.recv.side_effect = [b"X" * MAX_HEADER_SIZE, b"X"]
        with patch("wordpress_secure_https.create_verified_connection", return_value=connection):
            with self.assertRaisesRegex(InvalidHTTPResponse, "headers"):
                secure_https_get("example.com")
        connection.close.assert_called_once()

    def test_read_deadline_does_not_reset_for_each_chunk(self):
        connection = Mock()
        connection.recv.return_value = b"H"
        with patch("wordpress_secure_https.create_verified_connection", return_value=connection), patch(
            "wordpress_secure_https.time.monotonic", side_effect=[0, 1, 2, 16]
        ):
            with self.assertRaisesRegex(TimeoutError, "deadline"):
                secure_https_get("example.com", timeout=15)
        self.assertEqual(connection.recv.call_count, 1)
        connection.close.assert_called_once()

    def test_deadline_exceeded_during_connect(self):
        connection = Mock()
        with patch("wordpress_secure_https.create_verified_connection", return_value=connection), patch(
            "wordpress_secure_https.time.monotonic", side_effect=[0, 16]
        ):
            with self.assertRaises(TimeoutError):
                secure_https_get("example.com")
        connection.sendall.assert_not_called()
        connection.close.assert_called_once()

    def test_ipv6_host_header_brackets(self):
        connection = Mock()
        connection.recv.side_effect = [b"HTTP/1.1 204 No Content\r\n\r\n", b""]
        with patch("wordpress_secure_https.create_verified_connection", return_value=connection):
            secure_https_get("2606:4700:4700::1111")
        self.assertIn(b"Host: [2606:4700:4700::1111]\r\n", connection.sendall.call_args.args[0])

    def test_authentication_and_safe_session_remain_disabled(self):
        from wordpress_connection import WordPressConnection
        from wordpress_safe_transport import SafeTransportUnavailable, create_safe_session
        with patch("wordpress_adapter.requests.Session") as session:
            with self.assertRaisesRegex(RuntimeError, "authentication disabled"):
                WordPressConnection().verify("https://example.com", "user", "password")
            with self.assertRaises(SafeTransportUnavailable):
                create_safe_session()
            session.assert_not_called()


if __name__ == "__main__":
    unittest.main()


class TestDNSIntegration(unittest.TestCase):
    def test_resolve_uses_bounded_dns(self):
        with patch("wordpress_dns_deadline.getaddrinfo_with_deadline", return_value=fake_dns("8.8.8.8")) as dns:
            self.assertEqual(resolve_public_ips("example.com", timeout=3), ["8.8.8.8"])
            dns.assert_called_once_with("example.com", 443, timeout=3)

    def test_dns_timeout_blocks_tcp(self):
        from wordpress_dns_deadline import DNSDeadlineExceeded
        with patch("wordpress_dns_deadline.getaddrinfo_with_deadline", side_effect=DNSDeadlineExceeded("expired")), patch("wordpress_https_deadline.socket.create_connection") as tcp:
            with self.assertRaises(DNSDeadlineExceeded):
                create_verified_connection("example.com", timeout=2)
            tcp.assert_not_called()

    def test_dns_rejects_private_ip_before_tcp(self):
        with patch("wordpress_dns_deadline.getaddrinfo_with_deadline", return_value=fake_dns("10.0.0.1")), patch("wordpress_https_deadline.socket.create_connection") as tcp:
            with self.assertRaises(UnsafeDestinationError):
                create_verified_connection("example.com", timeout=2)
            tcp.assert_not_called()
