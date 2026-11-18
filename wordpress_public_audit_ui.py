"""Optional Streamlit UI for a read-only WordPress audit.

Only a user click triggers the public WordPress inventory request.
"""
from urllib.parse import urlsplit

from wordpress_public_audit import build_public_wordpress_audit
from wordpress_tls_diagnostics import classify_tls_failure


def _hostname_from_scan(start_url, rows):
    if not isinstance(start_url, str) or not isinstance(rows, list) or len(rows) > 30:
        raise ValueError("Invalid scan context")
    parsed = urlsplit(start_url if '://' in start_url else 'https://' + start_url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ValueError("WordPress public audit requires an HTTPS website")
    host = parsed.hostname.lower()
    if not rows:
        raise ValueError("Scan a page before starting the WordPress audit")
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get('page'), str):
            raise ValueError("Invalid Scanner row")
        page = urlsplit(row['page'])
        if page.hostname != host or page.username or page.password:
            raise ValueError("Scanner rows must belong to the selected website")
    return host


def render_public_wordpress_audit(rows, start_url, *, st_module=None):
    """Render opt-in public inventory and Advisor report; no site changes."""
    if st_module is None:
        import streamlit as st_module
    st_module.subheader('WordPress public inventory (optional)')
    st_module.caption('Read-only, published posts/pages only. No credentials or repairs.')
    if not st_module.button('Check public WordPress inventory', key='fg_wp_public_inventory'):
        return None
    try:
        hostname = _hostname_from_scan(start_url, rows)
        report = build_public_wordpress_audit(hostname, rows, per_page=20, timeout=15)
    except (ValueError, OSError, TimeoutError) as exc:
        # Never display raw network errors, which may contain host/IP details.
        if isinstance(exc, (ConnectionError, TimeoutError, OSError)):
            message = classify_tls_failure(exc)['message']
        else:
            message = 'The public WordPress inventory could not be validated or retrieved.'
        st_module.warning('WordPress public inventory unavailable: ' + message)
        return None
    coverage = report['inventory_coverage']
    st_module.write('Public entries sampled:', coverage['inventory_count'])
    st_module.write('Entries not attempted by Scanner:', coverage['not_scanned_count'])
    if coverage['not_scanned']:
        st_module.dataframe(coverage['not_scanned'], use_container_width=True, hide_index=True)
    if report['incomplete_scans']:
        st_module.caption('Some scan attempts did not provide usable HTML for SEO analysis.')
    if report['seo_recommendations']:
        st_module.dataframe(report['seo_recommendations'], use_container_width=True, hide_index=True)
    st_module.caption('Inventory coverage is not an SEO verdict. No automatic changes.')
    return report
