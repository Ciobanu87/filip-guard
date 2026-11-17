"""Offline HTTP request header validation for a future WordPress transport.

Does not open sockets or enable authenticated requests.
"""
import re

_NAME = re.compile(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+\Z", re.ASCII)


def validate_request_headers(headers):
    """Return validated immutable ASCII headers, rejecting unsafe input.

    Authorization is deliberately forbidden until the authenticated transport
    receives a separate security review. Caller cannot override Host or framing.
    """
    if not isinstance(headers, (tuple, list)) or len(headers) > 20:
        raise ValueError("Invalid request headers")
    checked = []
    seen = set()
    for item in headers:
        if not isinstance(item, (tuple, list)) or len(item) != 2:
            raise ValueError("Invalid request header")
        name, value = item
        if not isinstance(name, str) or not _NAME.fullmatch(name):
            raise ValueError("Invalid request header name")
        if not isinstance(value, str) or len(value) > 4096 or not value.isascii() or any(ord(c) < 32 or ord(c) == 127 for c in value):
            raise ValueError("Invalid request header value")
        lower = name.lower()
        if lower in seen or lower not in {"user-agent"}:
            raise ValueError("Unsupported or duplicate request header")
        seen.add(lower)
        checked.append((name, value))
    return tuple(checked)
