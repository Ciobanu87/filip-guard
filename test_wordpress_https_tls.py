"""Real local TLS tests; no public network or WordPress credentials needed."""

import shutil
import socket
import ssl
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from wordpress_secure_https import secure_https_get


@unittest.skipUnless(shutil.which("openssl"), "OpenSSL CLI required for TLS fixture")
class TestLocalHTTPSTransport(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        cls.cert = Path(cls.temp.name) / "cert.pem"
        cls.key = Path(cls.temp.name) / "key.pem"
        subprocess.run([
            "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
            "-days", "1", "-keyout", str(cls.key), "-out", str(cls.cert),
            "-subj", "/CN=example.test", "-addext", "subjectAltName=DNS:example.test",
        ], check=True, capture_output=True, timeout=15)

    def exchange(self, response, *, abrupt=False, hostname="example.test", trusted=True):
        server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        server_context.load_cert_chain(self.cert, self.key)
        client_context = ssl.create_default_context(cafile=str(self.cert) if trusted else None)
        listener = socket.socket()
        self.addCleanup(listener.close)
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        listener.settimeout(3)
        port = listener.getsockname()[1]
        requests = []
        errors = []

        def serve():
            try:
                raw, _ = listener.accept()
                with raw:
                    raw.settimeout(3)
                    try:
                        tls = server_context.wrap_socket(raw, server_side=True)
                    except ssl.SSLError:
                        # Certificate rejection is expected in the negative tests.
                        return
                    with tls:
                        request = bytearray()
                        while b"\r\n\r\n" not in request:
                            chunk = tls.recv(4096)
                            if not chunk:
                                raise AssertionError("Client closed before request headers")
                            request.extend(chunk)
                        requests.append(bytes(request))
                        tls.sendall(response)
                        if not abrupt:
                            try:
                                plain = tls.unwrap()  # Send TLS close_notify.
                            except ssl.SSLEOFError:
                                # The client closes its socket after receiving close_notify.
                                pass
                            else:
                                plain.close()
                        # SSLSocket.close() alone deliberately omits close_notify.
            except Exception as error:
                errors.append(error)

        worker = threading.Thread(target=serve, daemon=True)
        worker.start()
        real_connect = socket.create_connection

        def connect_pinned(address, timeout):
            self.assertEqual(address, ("8.8.8.8", 443))
            return real_connect(("127.0.0.1", port), timeout=timeout)

        try:
            # Only route the pinned TCP destination into our controlled fixture.
            # Actual TLS handshakes and hostname/certificate checks remain enabled.
            with patch("wordpress_secure_https.resolve_public_ips", return_value=["8.8.8.8"]), patch(
                "wordpress_secure_https.socket.create_connection", side_effect=connect_pinned
            ) as connect, patch("ssl.create_default_context", return_value=client_context):
                result = secure_https_get(hostname, "/wp-json/", timeout=3)
                connect.assert_called_once()
                return result, requests
        finally:
            worker.join(timeout=5)
            self.assertFalse(worker.is_alive(), "TLS fixture did not terminate")
            self.assertEqual(errors, [])

    def test_verified_tls_get_with_content_length(self):
        response = b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\n{}"
        result, requests = self.exchange(response)
        self.assertEqual(result, response)
        self.assertEqual(len(requests), 1)
        self.assertIn(b"Host: example.test\r\n", requests[0])
        self.assertNotIn(b"Authorization:", requests[0])

    def test_verified_tls_get_with_chunked_body(self):
        response = b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n2\r\n{}\r\n0\r\n\r\n"
        result, _ = self.exchange(response)
        self.assertEqual(result, response)

    def test_untrusted_certificate_rejected(self):
        with self.assertRaises(ConnectionError) as caught:
            self.exchange(b"", trusted=False)
        self.assertIsInstance(caught.exception.__cause__, ssl.SSLCertVerificationError)

    def test_certificate_hostname_mismatch_rejected(self):
        with self.assertRaises(ConnectionError) as caught:
            self.exchange(b"", hostname="other.test")
        self.assertIsInstance(caught.exception.__cause__, ssl.SSLCertVerificationError)

    def test_abrupt_tls_eof_rejected_without_content_length(self):
        with self.assertRaises(ssl.SSLEOFError):
            self.exchange(b"HTTP/1.1 200 OK\r\n\r\npartial", abrupt=True)


if __name__ == "__main__":
    unittest.main()
