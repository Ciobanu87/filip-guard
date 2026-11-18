"""Bounded, unauthenticated WordPress inventory for future read-only analysis.

Only the first page of published posts and pages is collected. No credentials,
site changes, background jobs or AutoFix are performed by this module.
"""
from urllib.parse import urlsplit

from wordpress_public_readonly import fetch_public_wordpress


class PublicInventoryError(ValueError):
    """A public WordPress inventory cannot be trusted or completed."""


def collect_public_inventory(hostname, *, per_page=20, timeout=15):
    """Return a validated inventory of public posts/pages from one host.

    Both requests must succeed; no partial inventory is returned on failure.
    Identifiers are unique per resource, not across WordPress resource types.
    The original validated URL is retained; no external URL is fetched.
    """
    # Fail before network if input is invalid; the lower-level HTTPS layer
    # independently validates the host and timeout before opening a socket.
    from wordpress_secure_https import _validate_request
    if type(per_page) is not int or not 1 <= per_page <= 100:
        raise PublicInventoryError("Invalid inventory page size")
    _validate_request(hostname, "/wp-json/wp/v2/posts", timeout)
    entries = []
    for resource in ("posts", "pages"):
        items = fetch_public_wordpress(hostname, resource, per_page=per_page, timeout=timeout)
        if not isinstance(items, list) or len(items) > per_page:
            raise PublicInventoryError("Unexpected inventory response size")
        for item in items:
            # Lower-level validator enforces published status, positive ID and
            # safe HTTPS links. Check the minimal contract again at the boundary.
            if (not isinstance(item, dict) or type(item.get("id")) is not int
                    or item["id"] <= 0 or item.get("status") != "publish"
                    or not isinstance(item.get("link"), str)):
                raise PublicInventoryError("Invalid inventory item")
            url = item["link"]
            parsed = urlsplit(url)
            if parsed.scheme != "https" or not parsed.hostname:
                raise PublicInventoryError("Invalid inventory link")
            entries.append({"resource": resource, "id": item["id"], "url": url})
    return entries
