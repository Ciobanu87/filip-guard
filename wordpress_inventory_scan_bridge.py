"""Offline comparison of a public WordPress inventory with existing Scanner rows.

Does not crawl, infer SEO findings, call AI Advisor, or modify WordPress.
The inventory contains URLs only; SEO analysis requires actual scanned HTML.
"""
from urllib.parse import urlsplit


class InvalidInventoryComparison(ValueError):
    """Inventory or scanner rows cannot be compared safely."""


def compare_inventory_to_scan(inventory, scan_rows):
    """Return bounded coverage details and URLs not present in scan rows.

    Matches exact URLs except fragments, preserving case and query strings.
    A scan row with any HTTP status (including ERROR) counts as attempted,
    not as successfully analyzed. This is coverage, never a health verdict.
    """
    if not isinstance(inventory, list) or len(inventory) > 200:
        raise InvalidInventoryComparison("Invalid inventory size")
    if not isinstance(scan_rows, list) or len(scan_rows) > 30:
        raise InvalidInventoryComparison("Invalid scan size")

    def canonical(value):
        if not isinstance(value, str) or len(value) > 4096:
            raise InvalidInventoryComparison("Invalid URL")
        try:
            parsed = urlsplit(value)
            if (parsed.scheme != 'https' or not parsed.hostname or parsed.username
                    or parsed.password or parsed.port not in (None, 443)
                    or parsed.fragment or any(ord(c) < 33 or ord(c) > 126 for c in value)):
                raise InvalidInventoryComparison("Unsafe URL")
        except ValueError as exc:
            raise InvalidInventoryComparison("Invalid URL") from exc
        return value

    scanned = set()
    for row in scan_rows:
        if not isinstance(row, dict) or 'page' not in row:
            raise InvalidInventoryComparison("Invalid scan row")
        scanned.add(canonical(row['page']))

    unseen = []
    observed = set()
    matched = 0
    for item in inventory:
        if (not isinstance(item, dict) or item.get('resource') not in ('posts', 'pages')
                or type(item.get('id')) is not int or item['id'] <= 0):
            raise InvalidInventoryComparison("Invalid inventory entry")
        url = canonical(item.get('url'))
        key = (item['resource'], item['id'])
        if key in observed:
            raise InvalidInventoryComparison("Duplicate inventory ID")
        observed.add(key)
        if url in scanned:
            matched += 1
        else:
            unseen.append({'resource': item['resource'], 'id': item['id'], 'url': url})
    return {'inventory_count': len(inventory), 'scan_attempted_count': matched,
            'not_scanned_count': len(unseen), 'not_scanned': unseen,
            'note': 'Coverage only: unscanned URLs are not SEO issues; scanned URLs may have failed.'}
