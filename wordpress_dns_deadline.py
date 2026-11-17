"""Bounded DNS lookup for unauthenticated FILIP GUARD HTTPS transport.

Python cannot forcibly cancel a running system getaddrinfo call. At most four
concurrent daemon workers are permitted; timed-out lookups never authorize a
connection and workers release capacity only after actually returning.
"""
import socket
import math
import threading
import time

_SLOTS = threading.BoundedSemaphore(4)


class DNSDeadlineExceeded(TimeoutError):
    """DNS lookup exceeded its deadline or resolver capacity was exhausted."""


def getaddrinfo_with_deadline(hostname, port=443, *, timeout=15):
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("DNS timeout must be positive")
    deadline = time.monotonic() + timeout
    if not _SLOTS.acquire(timeout=timeout):
        raise DNSDeadlineExceeded("DNS resolver capacity exhausted")
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        _SLOTS.release()
        raise DNSDeadlineExceeded("DNS deadline exceeded")
    finished = threading.Event()
    result = {}

    def lookup():
        try:
            result["value"] = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
        except BaseException as exc:
            result["error"] = exc
        finally:
            finished.set()
            _SLOTS.release()

    try:
        threading.Thread(target=lookup, daemon=True, name="fg-dns-resolver").start()
    except BaseException:
        _SLOTS.release()
        raise
    if not finished.wait(remaining):
        raise DNSDeadlineExceeded("DNS deadline exceeded")
    if "error" in result:
        raise result["error"]
    return result["value"]
