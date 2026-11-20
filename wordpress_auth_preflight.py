"""Offline preflight for WordPress Application Password inputs.

This module never sends credentials, authenticates a user, or enables AutoFix.
Its output is diagnostic only and must not be treated as proof of authorization.
"""
from dataclasses import dataclass
from urllib.parse import urlsplit
import re

_LABEL = re.compile(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\Z', re.ASCII)


class AuthPreflightError(ValueError):
    """Invalid WordPress connection input; does not expose secrets."""


@dataclass(frozen=True)
class AuthPreflightResult:
    hostname: str
    username: str
    credentials_present: bool
    remote_identity_verified: bool = False
    remote_write_authorized: bool = False


def validate_auth_preflight(site_url, username, app_password):
    """Check syntax only. Never return, log, or retain the password."""
    try:
        if not isinstance(site_url, str) or site_url != site_url.strip():
            raise ValueError()
        url = urlsplit(site_url)
        if (url.scheme != 'https' or not url.hostname or url.username is not None
                or url.password is not None or url.path not in ('', '/')
                or url.query or url.fragment or url.port not in (None, 443)):
            raise ValueError()
        hostname = url.hostname.rstrip('.').lower()
        if len(hostname) > 253 or not all(_LABEL.fullmatch(x) for x in hostname.split('.')):
            raise ValueError()
    except (ValueError, TypeError):
        raise AuthPreflightError('Invalid HTTPS WordPress site URL') from None
    if (not isinstance(username, str) or not username.strip()
            or len(username) > 128 or any(ord(c) < 32 or ord(c) == 127 for c in username)):
        raise AuthPreflightError('Invalid WordPress username')
    if (not isinstance(app_password, str) or not app_password.strip()
            or len(app_password) > 512 or any(ord(c) < 32 or ord(c) == 127 for c in app_password)):
        raise AuthPreflightError('Invalid application password')
    return AuthPreflightResult(hostname, username, True)
