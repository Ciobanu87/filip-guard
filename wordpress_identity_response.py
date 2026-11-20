"""Offline WordPress identity response inspection; never authenticates or authorizes.

A parsed HTTP response is untrusted until a separately reviewed authenticated
transport establishes provenance. No network calls or credentials are used here.
"""
from dataclasses import dataclass
from wordpress_secure_https import ValidatedHTTPResponse
from wordpress_identity_evidence import parse_wordpress_identity, WordPressIdentityError


class IdentityResponseError(ValueError):
    """HTTP response is unsuitable for offline identity diagnostics."""


@dataclass(frozen=True)
class IdentityResponseDiagnostic:
    user_id: int
    username: str
    display_name: str
    http_status: int
    remote_identity_verified: bool = False
    remote_write_authorized: bool = False


def inspect_identity_response(response):
    """Inspect an already parsed HTTP response without trusting its provenance."""
    if type(response) is not ValidatedHTTPResponse or response.status != 200:
        raise IdentityResponseError('Invalid WordPress identity response')
    headers = response.headers
    if type(headers) is not tuple or any(type(h) is not tuple or len(h) != 2 for h in headers):
        raise IdentityResponseError('Invalid WordPress identity response')
    types = [value.lower().split(';', 1)[0].strip() for key, value in headers if key.lower() == 'content-type']
    if types != ['application/json']:
        raise IdentityResponseError('Invalid WordPress identity content type')
    try:
        identity = parse_wordpress_identity(response.body)
    except WordPressIdentityError:
        raise IdentityResponseError('Invalid WordPress identity response') from None
    return IdentityResponseDiagnostic(identity.user_id, identity.username, identity.display_name, 200)
