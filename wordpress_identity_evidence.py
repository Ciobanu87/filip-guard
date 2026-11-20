"""Offline validation of a WordPress /wp/v2/users/me JSON response.

This parser does not authenticate a request, establish response provenance,
grant permissions, send credentials, or enable remote writes.
"""
import json
from dataclasses import dataclass


class WordPressIdentityError(ValueError):
    """Identity response is malformed or untrusted for diagnostic parsing."""


@dataclass(frozen=True)
class WordPressIdentity:
    user_id: int
    username: str
    display_name: str
    remote_identity_verified: bool = False
    remote_write_authorized: bool = False


def parse_wordpress_identity(body):
    """Parse a bounded UTF-8 JSON object for offline diagnostics only."""
    if type(body) is not bytes or len(body) > 65536:
        raise WordPressIdentityError("Invalid identity response")
    try:
        data = json.loads(body.decode("utf-8"))
    except (UnicodeError, ValueError, RecursionError):
        raise WordPressIdentityError("Invalid identity response") from None
    if type(data) is not dict:
        raise WordPressIdentityError("Invalid identity response")
    user_id = data.get("id")
    username = data.get("slug")
    display_name = data.get("name")
    if (type(user_id) is not int or user_id <= 0
            or type(username) is not str or not username or len(username) > 128
            or type(display_name) is not str or len(display_name) > 256
            or any(ord(c) < 32 or ord(c) == 127 for c in username + display_name)):
        raise WordPressIdentityError("Invalid identity response")
    return WordPressIdentity(user_id, username, display_name)
