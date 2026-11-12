
"""FILIP GUARD - WordPress URL security checks."""

import ipaddress
import socket
from urllib.parse import urlparse


def validate_public_wordpress_url(site_url):
    """Reject unsafe WordPress URLs and DNS destinations."""

    if not isinstance(site_url, str):
        raise ValueError("Invalid WordPress URL.")

    parsed = urlparse(site_url.strip())

    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in ("", "/")
    ):
        raise ValueError("A valid HTTPS URL is required.")

    try:
        port = parsed.port
    except ValueError:
        raise ValueError("Invalid URL port.")

    if port not in (None, 443):
        raise ValueError("Only HTTPS port 443 is allowed.")

    hostname = parsed.hostname

    if hostname == "localhost" or hostname.endswith(".localhost"):
        raise ValueError("Local addresses are blocked.")

    try:
        addresses = socket.getaddrinfo(
            hostname,
            443,
            type=socket.SOCK_STREAM,
        )
    except socket.gaierror:
        raise ValueError("Cannot resolve website hostname.")

    if not addresses:
        raise ValueError("No IP addresses found.")

    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])

        if not ip.is_global:
            raise ValueError(
                "Private or reserved IP addresses are blocked."
            )

    return parsed.geturl().rstrip("/")
