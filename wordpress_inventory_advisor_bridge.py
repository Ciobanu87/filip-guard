"""Read-only advisor report from existing scan findings and WP inventory coverage.

Inventory URLs alone never generate SEO findings. This module does not fetch,
modify, authenticate, or schedule anything.
"""
from ai_advisor import analyze_pages
from wordpress_inventory_scan_bridge import compare_inventory_to_scan


class InvalidAdvisorBridge(ValueError):
    """Scan findings cannot be safely combined with inventory coverage."""


def build_inventory_advisor_report(inventory, scan_rows):
    """Return existing SEO recommendations and separate inventory coverage.

    The existing advisor is invoked only for successfully scanned HTML pages.
    An attempted scan that failed or returned non-HTML cannot support SEO
    claims; such rows are reported separately for manual review.
    """
    coverage = compare_inventory_to_scan(inventory, scan_rows)
    eligible = []
    incomplete = []
    for row in scan_rows:
        status = row.get('http_status')
        # Scanner uses integer HTTP codes; failed/non-HTML pages lack SEO data.
        if type(status) is not int or not 200 <= status < 300 or row.get('issues') == 'Non-HTML or empty page':
            incomplete.append({'page': row['page'], 'http_status': status})
            continue
        eligible.append(row)
    recommendations = analyze_pages(eligible)
    if not isinstance(recommendations, list):
        raise InvalidAdvisorBridge('Unexpected advisor output')
    for rec in recommendations:
        if not isinstance(rec, dict) or rec.get('autofix') is not False:
            raise InvalidAdvisorBridge('Advisor output must remain read-only')
    return {
        'seo_recommendations': recommendations,
        'inventory_coverage': coverage,
        'incomplete_scans': incomplete,
        'note': ('Only successful HTML scans support SEO recommendations. '
                 'Inventory-only URLs and incomplete scans require further scanning; '
                 'no site changes are made.'),
        'autofix': False,
    }
