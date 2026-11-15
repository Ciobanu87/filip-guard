
"""FILIP GUARD - Secure HTTPS utilities."""

import ipaddress
import socket


class UnsafeDestinationError(ValueError):
    """Destination is not safe for connection."""


def resolve_public_ips(hostname):
    """Resolve hostname and reject non-public IPs."""
    if not hostname:
        raise UnsafeDestinationError("Missing hostname.")

    results = socket.getaddrinfo(
        hostname,
        443,
        type=socket.SOCK_STREAM,
    )

    addresses = set()

    for result in results:
        address = result[4][0]
        ip = ipaddress.ip_address(address)

        if not ip.is_global:
            raise UnsafeDestinationError(
                "Private or reserved IP blocked."
            )

        addresses.add(str(ip))

    if not addresses:
        raise UnsafeDestinationError(
            "No public IP addresses found."
        )

    return sorted(addresses)



def create_verified_connection(hostname, timeout=15):
    """Open TLS connection to a verified public IP."""
    import socket
    import ssl

    addresses = resolve_public_ips(hostname)
    last_error = None

    for address in addresses:
        try:
            connection = socket.create_connection(
                (address, 443),
                timeout=timeout,
            )

            try:
                context = ssl.create_default_context()
                return context.wrap_socket(
                    connection,
                    server_hostname=hostname,
                )
            except Exception:
                connection.close()
                raise

        except (OSError, ssl.SSLError) as exc:
            last_error = exc

    raise ConnectionError(
        "Could not establish a secure HTTPS connection."
    ) from last_error



def secure_https_get(hostname, path="/", timeout=15):
    """Send a GET request over verified TLS."""
    if not isinstance(path, str) or not path.startswith("/"):
        raise ValueError("Invalid HTTPS path.")

    if any(c in path for c in "\r\n"):
        raise ValueError("Invalid characters in path.")

    connection = create_verified_connection(
        hostname,
        timeout=timeout,
    )

    try:
        request = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {hostname}\r\n"
            "Accept: application/json\r\n"
            "Connection: close\r\n"
            "\r\n"
        )

        connection.sendall(request.encode("ascii"))

        chunks = []
        while True:
            chunk = connection.recv(65536)
            if not chunk:
                break
            chunks.append(chunk)

        return b"".join(chunks)
    finally:
        connection.close()
