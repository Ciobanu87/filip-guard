
"""Authorization checks for FILIP GUARD.

This module does not authenticate users or change websites.
"""

from dataclasses import dataclass
from hmac import compare_digest
from urllib.parse import urlparse


@dataclass(frozen=True)
class RepairApproval:
    site_url: str
    resource_id: int
    original_hash: str
    proposed_hash: str
    authorized: bool
    approved: bool


def _host(url):
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("A valid HTTPS URL is required.")
    if parsed.username or parsed.password:
        raise ValueError("Credentials in URLs are not allowed.")
    return parsed.hostname.lower()


def validate_approval(approval, target_url,
                      resource_id, original_hash,
                      proposed_hash):
    """Validate a declared approval for one exact change."""

    if not isinstance(approval, RepairApproval):
        return False

    if approval.authorized is not True:
        return False

    if approval.approved is not True:
        return False

    try:
        if _host(approval.site_url) != _host(target_url):
            return False
    except (ValueError, TypeError):
        return False

    if type(resource_id) is not int or resource_id <= 0:
        return False

    if approval.resource_id != resource_id:
        return False

    if not all(
        isinstance(value, str) and len(value) == 64
        for value in (
            original_hash,
            proposed_hash,
            approval.original_hash,
            approval.proposed_hash,
        )
    ):
        return False

    return (
        compare_digest(approval.original_hash, original_hash)
        and compare_digest(approval.proposed_hash, proposed_hash)
    )
