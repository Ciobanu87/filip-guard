"""Offline WordPress capability evidence checks (never authorizes remote writes).

Evidence must originate from a separately authenticated and trusted transport.
This module cannot establish authenticity or freshness.
"""
from dataclasses import dataclass
from urllib.parse import urlsplit
import re


class CapabilityEvidenceError(PermissionError):
    pass


@dataclass(frozen=True)
class CapabilityEvidence:
    user_id: int
    site_url: str
    resource_id: int
    resource_type: str
    can_edit: bool
    can_edit_others: bool = False


def _origin(url):
    if not isinstance(url, str) or not url or url != url.strip():
        raise CapabilityEvidenceError('Invalid authorization target')
    try:
        p = urlsplit(url)
        if (p.scheme != 'https' or not p.hostname or p.username is not None
                or p.password is not None or p.query or p.fragment
                or p.path not in ('', '/') or p.port not in (None, 443)):
            raise ValueError()
        host = p.hostname.rstrip('.').lower()
        if (len(host) > 253 or not all(
            re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', label)
            for label in host.split('.')
        )):
            raise ValueError()
        return host
    except (ValueError, TypeError):
        raise CapabilityEvidenceError('Invalid authorization target') from None


def validate_capability_evidence(evidence, *, site_url, user_id,
                                 resource_id, resource_type):
    """Validate offline metadata only; never grant WordPress write access."""
    if type(evidence) is not CapabilityEvidence:
        raise CapabilityEvidenceError('Trusted WordPress evidence required')
    if (type(user_id) is not int or user_id <= 0 or
            type(resource_id) is not int or resource_id <= 0 or
            resource_type not in ('post', 'page')):
        raise CapabilityEvidenceError('Invalid authorization target')
    expected_origin = _origin(site_url)
    evidence_origin = _origin(evidence.site_url)
    if (type(evidence.user_id) is not int or evidence.user_id != user_id or
            expected_origin != evidence_origin or
            type(evidence.resource_id) is not int or evidence.resource_id != resource_id or
            evidence.resource_type != resource_type or
            evidence.can_edit is not True):
        raise CapabilityEvidenceError('WordPress capability evidence mismatch')
    return {'offline_capability_check': True, 'remote_write_authorized': False}
