"""Offline approval metadata checks; NOT user authentication or write authorization."""
from dataclasses import dataclass
from hmac import compare_digest
import re
from urllib.parse import urlsplit

@dataclass(frozen=True)
class RepairApproval:
    site_url: str
    resource_id: int
    original_hash: str
    proposed_hash: str
    authorized: bool
    approved: bool

def _site_identity(url):
    if not isinstance(url, str) or not url or url != url.strip():
        raise ValueError('Invalid site URL')
    try:
        parsed = urlsplit(url)
        if (parsed.scheme != 'https' or not parsed.hostname or parsed.username is not None
                or parsed.password is not None or parsed.query or parsed.fragment
                or parsed.path not in ('', '/') or parsed.port not in (None, 443)):
            raise ValueError('Invalid HTTPS site origin')
        host = parsed.hostname.lower().rstrip('.')
        if not host or any(ord(c) < 33 or ord(c) > 126 for c in host):
            raise ValueError('Invalid hostname')
        if not re.fullmatch(r'[a-z0-9.-]+', host) or '..' in host:
            raise ValueError('Invalid hostname')
        return host
    except (ValueError, TypeError):
        raise ValueError('Invalid HTTPS site origin') from None

def validate_approval(approval, target_url, resource_id, original_hash, proposed_hash):
    """Check declared metadata only; a trusted service must authenticate approval."""
    if type(approval) is not RepairApproval or approval.authorized is not True or approval.approved is not True:
        return False
    try:
        if _site_identity(approval.site_url) != _site_identity(target_url):
            return False
    except ValueError:
        return False
    if type(resource_id) is not int or resource_id <= 0 or type(approval.resource_id) is not int or approval.resource_id != resource_id:
        return False
    hashes = (original_hash, proposed_hash, approval.original_hash, approval.proposed_hash)
    if not all(isinstance(h, str) and re.fullmatch(r'[0-9a-f]{64}', h) for h in hashes):
        return False
    return (compare_digest(approval.original_hash, original_hash)
            and compare_digest(approval.proposed_hash, proposed_hash))
