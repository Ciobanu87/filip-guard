
"""FILIP GUARD - Secure HTTPS utilities."""

import ipaddress
import math
import re
import socket
import time
from dataclasses import dataclass


class UnsafeDestinationError(ValueError):
    """Destination is not safe for connection."""


def resolve_public_ips(hostname, *, timeout=15):
    """Resolve hostname and reject non-public IPs."""
    if not hostname:
        raise UnsafeDestinationError("Missing hostname.")

    from wordpress_dns_deadline import getaddrinfo_with_deadline
    results = getaddrinfo_with_deadline(hostname, 443, timeout=timeout)

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
    """Open verified TLS to a DNS-pinned public IP with one connect budget.

    System DNS remains synchronous and cannot be forcibly cancelled here.
    """
    from wordpress_https_deadline import Deadline, connect_pinned_addresses

    deadline = Deadline(timeout)
    addresses = resolve_public_ips(hostname, timeout=deadline.remaining())
    return connect_pinned_addresses(hostname, addresses, deadline)


MAX_RESPONSE_SIZE = 2 * 1024 * 1024
MAX_HEADER_SIZE = 64 * 1024
MAX_LINE_SIZE = 8192
MAX_HEADER_COUNT = 100
_TOKEN = rb"[!#$%&'*+.^_`|~0-9A-Za-z-]+"


class InvalidHTTPResponse(ValueError):
    """The peer sent an invalid or unsupported HTTP response."""


@dataclass(frozen=True)
class ValidatedHTTPResponse:
    status: int
    headers: tuple[tuple[str, str], ...]
    body: bytes


def _decode_chunked(body):
    """Decode bounded chunk framing; extensions and trailers fail closed."""
    chunks = []
    offset = 0
    while True:
        end = body.find(b"\r\n", offset)
        if end < 0 or end - offset > MAX_LINE_SIZE:
            raise InvalidHTTPResponse("Missing or oversized chunk size line.")
        size_line = body[offset:end]
        # No int conversion of unbounded attacker-controlled strings.
        if not re.fullmatch(rb"[0-9A-Fa-f]{1,16}", size_line):
            raise InvalidHTTPResponse("Invalid or unsupported chunk size.")
        size = int(size_line, 16)
        offset = end + 2
        if size == 0:
            if body[offset:] != b"\r\n":
                raise InvalidHTTPResponse("Trailers or trailing response data blocked.")
            return b"".join(chunks)
        if size > MAX_RESPONSE_SIZE or offset + size + 2 > len(body):
            raise InvalidHTTPResponse("Truncated or oversized HTTP chunk.")
        if body[offset + size:offset + size + 2] != b"\r\n":
            raise InvalidHTTPResponse("Invalid chunk delimiter.")
        chunks.append(body[offset:offset + size])
        offset += size + 2


def parse_http_response(raw):
    """Validate one complete GET response using a strict HTTP/1.x subset.

    Accepts Content-Length, plain chunked, or connection-close framing.
    Rejects ambiguous framing, redirects, informational responses, compression,
    chunk extensions and trailers. HTTP error statuses remain available to the
    future adapter; protocol validity does not imply WordPress/API success.
    See RFC 9112 sections 4-7. This is not a general-purpose HTTP client.
    """
    if not isinstance(raw, bytes):
        raise TypeError("HTTP response must be bytes.")
    if len(raw) > MAX_RESPONSE_SIZE:
        raise InvalidHTTPResponse("HTTPS response too large.")
    boundary = raw.find(b"\r\n\r\n")
    if boundary < 0 or boundary + 4 > MAX_HEADER_SIZE:
        raise InvalidHTTPResponse("Missing or oversized HTTP headers.")
    lines = raw[:boundary].split(b"\r\n")
    if any(len(line) > MAX_LINE_SIZE for line in lines):
        raise InvalidHTTPResponse("HTTP header line too large.")
    match = re.fullmatch(
        rb"HTTP/1\.[01] ([2-5][0-9]{2}) [\t\x20-\x7e\x80-\xff]*", lines[0]
    )
    if not match:
        raise InvalidHTTPResponse("Invalid or unsupported HTTP status line.")
    status = int(match[1])
    if 300 <= status < 400:
        raise InvalidHTTPResponse("HTTP redirects are disabled.")
    if len(lines) - 1 > MAX_HEADER_COUNT:
        raise InvalidHTTPResponse("Too many HTTP headers.")
    headers = []
    fields = {}
    for line in lines[1:]:
        name, separator, value = line.partition(b":")
        if not separator or not re.fullmatch(_TOKEN, name):
            raise InvalidHTTPResponse("Invalid HTTP header name or folding.")
        if re.search(rb"[\x00-\x08\x0a-\x1f\x7f]", value):
            raise InvalidHTTPResponse("Invalid HTTP header value.")
        key = name.decode("ascii").lower()
        value = value.strip(b" \t").decode("latin-1")
        headers.append((key, value))
        fields.setdefault(key, []).append(value)

    length = fields.get("content-length")
    transfer = fields.get("transfer-encoding")
    if length and transfer:
        raise InvalidHTTPResponse("Ambiguous HTTP body framing.")
    if length and (len(length) != 1 or not re.fullmatch(r"[0-9]{1,10}", length[0])):
        raise InvalidHTTPResponse("Invalid or duplicate Content-Length.")
    if transfer and ([v.lower() for v in transfer] != ["chunked"] or lines[0].startswith(b"HTTP/1.0")):
        raise InvalidHTTPResponse("Unsupported or duplicate Transfer-Encoding.")
    if [v.lower() for v in fields.get("content-encoding", ["identity"])] != ["identity"]:
        raise InvalidHTTPResponse("Compressed HTTP responses are disabled.")
    if "trailer" in fields or "upgrade" in fields:
        raise InvalidHTTPResponse("HTTP trailers and protocol upgrades are disabled.")

    body = raw[boundary + 4:]
    if status == 204:
        if length or transfer or body:
            raise InvalidHTTPResponse("HTTP 204 must not contain body framing or data.")
    elif transfer:
        body = _decode_chunked(body)
    elif length and int(length[0]) != len(body):
        raise InvalidHTTPResponse("Content-Length does not match HTTP body.")
    if status == 205 and body:
        raise InvalidHTTPResponse("HTTP 205 must not contain body data.")
    return ValidatedHTTPResponse(status, tuple(headers), body)


def _validate_request(hostname, path, timeout):
    """Reject request/header injection before DNS or connection creation."""
    if not isinstance(hostname, str) or not hostname or len(hostname) > 253 or "%" in hostname:
        raise ValueError("Invalid HTTPS hostname.")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        labels = hostname.removesuffix(".").split(".")
        if not all(re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label)
                   for label in labels):
            raise ValueError("Invalid HTTPS hostname.")
        host_header = hostname
    else:
        host_header = f"[{hostname}]" if address.version == 6 else hostname
    if (not isinstance(path, str) or not path.startswith("/")
            or path.startswith("//") or len(path) > MAX_LINE_SIZE
            or re.search(r"[^\x21-\x7e]|[#\\]", path)):
        raise ValueError("Invalid HTTPS path.")
    if (isinstance(timeout, bool) or not isinstance(timeout, (int, float))
            or not math.isfinite(timeout) or timeout <= 0):
        raise ValueError("HTTPS timeout must be positive and finite.")
    return host_header


def secure_https_get(hostname, path="/", timeout=15):
    """Return validated raw HTTP bytes from an unauthenticated HTTPS GET.

    No redirects or credentials. Total wire response is limited to 2 MiB.
    The I/O deadline includes connect time but cannot interrupt system DNS.
    Abrupt TLS EOF is rejected, including for connection-close framing.
    """
    host_header = _validate_request(hostname, path, timeout)
    deadline = time.monotonic() + timeout
    connection = create_verified_connection(hostname, timeout=timeout)

    def remaining_timeout():
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("HTTPS operation deadline exceeded.")
        connection.settimeout(remaining)

    try:
        request = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host_header}\r\n"
            "Accept: application/json\r\n"
            "Accept-Encoding: identity\r\n"
            "Connection: close\r\n"
            "\r\n"
        )
        remaining_timeout()
        connection.sendall(request.encode("ascii"))
        raw = bytearray()
        header_end = -1
        while True:
            remaining_timeout()
            chunk = connection.recv(min(65536, MAX_RESPONSE_SIZE + 1 - len(raw)))
            if not chunk:
                break
            raw.extend(chunk)
            if len(raw) > MAX_RESPONSE_SIZE:
                raise InvalidHTTPResponse("HTTPS response too large.")
            if header_end < 0:
                header_end = raw.find(b"\r\n\r\n")
                if ((header_end < 0 and len(raw) > MAX_HEADER_SIZE)
                        or header_end + 4 > MAX_HEADER_SIZE):
                    raise InvalidHTTPResponse("Missing or oversized HTTP headers.")
        response = bytes(raw)
        parse_http_response(response)
        return response
    finally:
        connection.close()
