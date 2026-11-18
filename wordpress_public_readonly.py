"""Unauthenticated, public WordPress REST discovery (posts and pages only).

No credentials, WordPress mutations, redirects or automatic repair are enabled.
"""
from wordpress_readonly_endpoints import readonly_path
from wordpress_readonly_pipeline import validate_readonly_exchange
from wordpress_secure_https import secure_https_get, _validate_request


def fetch_public_wordpress(hostname, resource, *, per_page=20, timeout=15):
    """Return validated public published posts/pages from a verified HTTPS host.

    This is a low-level read-only building block, not a production UI feature.
    """
    if type(resource) is not str or resource not in ("posts", "pages"):
        raise ValueError("Only public posts/pages are permitted")
    path = readonly_path(resource, per_page=per_page)
    _validate_request(hostname, path, timeout)
    raw_response = secure_https_get(hostname, path, timeout=timeout)
    checked_path, data = validate_readonly_exchange(resource, raw_response, per_page=per_page)
    if checked_path != path:
        raise RuntimeError("WordPress endpoint validation mismatch")
    return data
