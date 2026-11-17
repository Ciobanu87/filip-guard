"""Shared monotonic deadline for future FILIP GUARD HTTPS connections.

This module is standalone and does not enable WordPress authentication.
System getaddrinfo() is synchronous and is NOT bounded by this deadline.
"""
import math
import socket
import ssl
import time


class DeadlineExceeded(TimeoutError):
    """The operation exhausted its shared time budget."""


class Deadline:
    def __init__(self, timeout):
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("Timeout must be finite and positive")
        self.ends_at = time.monotonic() + timeout

    def remaining(self):
        value = self.ends_at - time.monotonic()
        if value <= 0:
            raise DeadlineExceeded("HTTPS deadline exceeded")
        return value


def connect_pinned_addresses(hostname, public_ips, deadline, *, context=None):
    """Try previously validated public IPs under ONE deadline.

    Caller must validate every resolved IP before calling this function.
    No DNS lookup, redirect, credentials or HTTP request occurs here.
    """
    if not public_ips:
        raise ValueError("No validated public IP addresses")
    if context is None:
        context = ssl.create_default_context()
    last_error = None
    for ip in public_ips:
        # An exhausted deadline must never trigger another connection.
        remaining = deadline.remaining()
        raw = None
        try:
            raw = socket.create_connection((ip, 443), timeout=remaining)
            raw.settimeout(deadline.remaining())
            tls = context.wrap_socket(raw, server_hostname=hostname, suppress_ragged_eofs=False,
                                      do_handshake_on_connect=False)
            raw = None  # TLS socket owns the underlying socket now.
            try:
                tls.settimeout(deadline.remaining())
                tls.do_handshake()
                tls.settimeout(deadline.remaining())
                return tls
            except BaseException:
                tls.close()
                raise
        except (OSError, ssl.SSLError) as exc:
            last_error = exc
        finally:
            if raw is not None:
                raw.close()
    raise ConnectionError("Verified TLS connection failed") from last_error
