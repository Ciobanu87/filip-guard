"""Opt-in public WordPress inventory + existing Scanner/Advisor report.

No credentials, editing, crawling, or scheduled operations. Scanner rows are
provided by the caller; this module never requests their URLs.
"""
from wordpress_public_inventory import collect_public_inventory
from wordpress_inventory_advisor_bridge import build_inventory_advisor_report
from wordpress_secure_https import _validate_request


def build_public_wordpress_audit(hostname, scan_rows, *, per_page=20, timeout=15):
    """Build an all-or-nothing read-only audit from already-scanned rows.

    WordPress inventory is capped at two resource lists of ``per_page`` items.
    The caller is responsible for obtaining authorized Scanner rows.
    """
    if not isinstance(scan_rows, list) or len(scan_rows) > 30:
        raise ValueError('Expected at most 30 Scanner rows')
    if any(not isinstance(row, dict) for row in scan_rows):
        raise ValueError('Invalid Scanner row')
    if type(per_page) is not int or not 1 <= per_page <= 100:
        raise ValueError('Invalid page limit')
    _validate_request(hostname, '/wp-json/wp/v2/posts', timeout)
    inventory = collect_public_inventory(hostname, per_page=per_page, timeout=timeout)
    report = build_inventory_advisor_report(inventory, scan_rows)
    if report.get('autofix') is not False:
        raise ValueError('Automatic repair must remain disabled')
    return report
