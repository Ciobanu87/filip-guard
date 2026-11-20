"""Additional fail-closed gate for future WordPress writes.

This module never sends requests or changes a website. Its approval must be
issued by a trusted server-side component after authenticated authorization;
client-provided booleans or dataclasses alone are not proof of authorization.
"""
from dataclasses import dataclass
from hashlib import sha256
from hmac import compare_digest
from urllib.parse import urlsplit
import re
import time

_HASH = re.compile(r'[0-9a-f]{64}\Z')

@dataclass(frozen=True)
class VerifiedChange:
    site_url: str
    resource_id: int
    user_id: int
    original_hash: str
    proposed_hash: str
    approved_at: float
    expires_at: float
    approval_id: str


def _origin(url):
    if not isinstance(url, str):
        raise ValueError('Invalid site URL')
    p = urlsplit(url)
    if (p.scheme != 'https' or not p.hostname or p.username or p.password
            or p.port not in (None, 443) or p.path not in ('', '/')
            or p.query or p.fragment):
        raise ValueError('Invalid site URL')
    host = p.hostname.rstrip('.').lower()
    if len(host) > 253 or not all(re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', label) for label in host.split('.')):
        raise ValueError('Invalid hostname')
    return host


def verify_prewrite(approval, *, site_url, resource_id, user_id,
                    current_content, proposed_content, now=None):
    """Validate a trusted approval and reject stale edits; does NOT authorize writes alone.

    Caller must separately verify approval_id against a server-side,
    single-use approval store bound to an authenticated user/session.
    """
    if not isinstance(approval, VerifiedChange):
        raise PermissionError('Missing verified approval')
    if (type(resource_id) is not int or resource_id <= 0
            or type(user_id) is not int or user_id <= 0
            or approval.resource_id != resource_id or approval.user_id != user_id):
        raise PermissionError('Resource or user mismatch')
    if _origin(approval.site_url) != _origin(site_url):
        raise PermissionError('Site mismatch')
    if not isinstance(approval.approval_id, str) or not approval.approval_id:
        raise PermissionError('Missing approval identifier')
    if (not isinstance(current_content, str) or not isinstance(proposed_content, str)
            or not all(isinstance(h, str) and _HASH.fullmatch(h)
                       for h in (approval.original_hash, approval.proposed_hash))):
        raise ValueError('Invalid content or hash')
    current = sha256(current_content.encode('utf-8')).hexdigest()
    proposed = sha256(proposed_content.encode('utf-8')).hexdigest()
    if current == proposed:
        raise ValueError('No changes')
    if not (compare_digest(current, approval.original_hash)
            and compare_digest(proposed, approval.proposed_hash)):
        raise PermissionError('Stale or modified content')
    instant = time.time() if now is None else now
    if not (approval.approved_at <= instant < approval.expires_at
            and approval.expires_at - approval.approved_at <= 900):
        raise PermissionError('Approval expired or invalid')
    return True
