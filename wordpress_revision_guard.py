"""Offline compare-before-write guard; does not authorize or execute remote writes.

The caller must obtain the remote snapshot and revision from an authenticated,
trusted WordPress request immediately before a future conditional update.
"""
from dataclasses import dataclass
from hashlib import sha256
from hmac import compare_digest
from urllib.parse import urlsplit


class RevisionMismatchError(RuntimeError):
    """The WordPress resource no longer matches the approved snapshot."""


@dataclass(frozen=True)
class ResourceSnapshot:
    site_url: str
    resource_type: str
    resource_id: int
    content: str
    revision: str


def verify_unchanged(approved, observed):
    """Check exact target, content, and revision. Never grants write permission.

    A matching result is insufficient for an atomic update: the future write
    transport MUST enforce a server-side precondition to close the TOCTOU gap.
    """
    if not isinstance(approved, ResourceSnapshot) or not isinstance(observed, ResourceSnapshot):
        raise RevisionMismatchError('Both snapshots are required')
    for snapshot in (approved, observed):
        if not isinstance(snapshot.site_url, str):
            raise RevisionMismatchError('Invalid resource site')
        try:
            url = urlsplit(snapshot.site_url)
            valid_site = (url.scheme == 'https' and bool(url.hostname) and
                          url.username is None and url.password is None and
                          not url.path and not url.query and not url.fragment and
                          url.port in (None, 443))
        except ValueError:
            valid_site = False
        if (not valid_site or
                snapshot.resource_type not in ('post', 'page') or
                type(snapshot.resource_id) is not int or snapshot.resource_id <= 0 or
                not isinstance(snapshot.content, str) or
                not isinstance(snapshot.revision, str) or
                not snapshot.revision.strip()):
            raise RevisionMismatchError('Invalid resource snapshot')
    if (approved.site_url != observed.site_url or
            approved.resource_type != observed.resource_type or
            approved.resource_id != observed.resource_id):
        raise RevisionMismatchError('Resource identity changed')
    old_hash = sha256(approved.content.encode('utf-8')).digest()
    new_hash = sha256(observed.content.encode('utf-8')).digest()
    if (not compare_digest(old_hash, new_hash) or
            not compare_digest(approved.revision, observed.revision)):
        raise RevisionMismatchError('Resource changed since approval')
    return {'unchanged_for_offline_review': True, 'remote_write_authorized': False}
