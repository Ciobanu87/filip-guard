"""Offline validation of WordPress authorization evidence; never performs network I/O.

Evidence must be supplied by a separately authenticated, trusted transport.
This module does not establish the authenticity or freshness of that evidence.
"""
from dataclasses import dataclass


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


def validate_capability_evidence(evidence, *, site_url, user_id,
                                 resource_id, resource_type):
    """Fail closed on absent/mismatched/insufficient offline evidence.

    The caller MUST verify origin, session identity, freshness, resource ownership
    and permissions with WordPress before trusting the supplied values.
    """
    if not isinstance(evidence, CapabilityEvidence):
        raise CapabilityEvidenceError('Trusted WordPress evidence required')
    if (type(user_id) is not int or user_id <= 0 or
            type(resource_id) is not int or resource_id <= 0 or
            not isinstance(site_url, str) or not site_url.startswith('https://') or
            resource_type not in ('post', 'page')):
        raise CapabilityEvidenceError('Invalid authorization target')
    if (type(evidence.user_id) is not int or evidence.user_id != user_id or
            evidence.site_url != site_url or
            type(evidence.resource_id) is not int or evidence.resource_id != resource_id or
            evidence.resource_type != resource_type or
            evidence.can_edit is not True):
        raise CapabilityEvidenceError('WordPress capability evidence mismatch')
    return {'offline_capability_check': True, 'remote_write_authorized': False}
