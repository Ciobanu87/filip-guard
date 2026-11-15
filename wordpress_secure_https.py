
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
