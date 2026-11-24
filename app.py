import csv
import io
import ipaddress
import socket
import time
from collections import deque
from urllib.parse import urljoin, urlparse, urldefrag

import requests
import streamlit as st
from bs4 import BeautifulSoup
from ai_advisor import analyze_pages, suggest_meta_description
from website_scanner import HEADERS, MAX_BYTES, public_host, validate_url, fetch, normalize_link, scan
from link_resolver import suggest_replacements
from wordpress_autofix_ui import render_wordpress_autofix_ui
from wordpress_autofix_sandbox_ui import render_autofix_sandbox
from customer_account_ui import render_customer_account
from guard_application_ui import render_guard_application
from monitoring_ui import render_monitoring
from wordpress_public_audit_ui import render_public_wordpress_audit

st.set_page_config(page_title='FILIP GUARD | Website Health & SEO', page_icon='🛡️', layout='centered')
st.title('🛡️ FILIP GUARD')
st.caption('Website Health & SEO • Beta')
st.write('Audit up to 30 public pages, find basic SEO issues and check internal links.')

if render_guard_application():
    st.stop()

render_customer_account()


def wordpress_public_items(site_host):
    """Read a small, bounded sample of public WP REST API content; never edit."""
    items = []
    for kind in ('pages', 'posts'):
        endpoint = f'https://{site_host}/wp-json/wp/v2/{kind}?per_page=30&_fields=link,slug,title,status'
        try:
            validate_url(endpoint, site_host)
            response = requests.get(endpoint, headers=HEADERS, timeout=(4, 8),
                                    allow_redirects=False, stream=True)
            try:
                if response.status_code != 200 or 'json' not in response.headers.get('Content-Type', '').lower():
                    continue
                chunks = bytearray()
                for chunk in response.iter_content(chunk_size=16384):
                    chunks.extend(chunk)
                    if len(chunks) > MAX_BYTES:
                        raise ValueError('WordPress API response too large')
                import json
                data = json.loads(chunks)
                if isinstance(data, list):
                    items.extend(item for item in data if isinstance(item, dict))
            finally:
                response.close()
        except (requests.RequestException, ValueError, UnicodeError):
            continue
    return items


def verified_wordpress_suggestions(broken):
    """Read-only suggestions; verify URLs and require human review."""
    if not broken:
        return []
    host = urlparse(broken[0]['link']).hostname
    if not host:
        return []
    items = wordpress_public_items(host)
    if not items:
        return []
    suggestions = []
    for issue in broken[:5]:
        broken_url = issue['link']
        if urlparse(broken_url).hostname != host:
            continue
        for match in suggest_replacements(broken_url, items, limit=3):
            candidate = match['candidate_url']
            try:
                status, _, _ = fetch(candidate, host, 'HEAD')
                if status in (403, 405, 501):
                    status, _, _ = fetch(candidate, host, 'GET')
                if 200 <= status < 400:
                    match['verified'] = True
                    suggestions.append(match)
            except (requests.RequestException, ValueError):
                continue
    return suggestions


def to_csv(rows):
    if not rows:
        return ''
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue()

with st.form('audit'):
    url = st.text_input('Website URL', placeholder='https://example.com')
    pages = st.slider('Maximum pages', 1, 30, 10)
    submitted = st.form_submit_button('🔎 Scan website', type='primary')

if submitted:
    st.session_state.pop('fg_scan_result', None)
    if not url.strip():
        st.warning('Enter a website URL.')
    else:
        try:
            with st.spinner('Scanning public pages. This may take a little while…'):
                rows, broken, checked, discovered = scan(url.strip(), pages)
            candidates = verified_wordpress_suggestions(broken) if broken else []
            st.session_state['fg_scan_result'] = {
                'start_url': url.strip(), 'rows': rows, 'broken': broken,
                'checked': checked, 'discovered': discovered, 'candidates': candidates,
            }
        except (ValueError, requests.RequestException) as exc:
            st.error(f'Could not scan: {exc}')

result = st.session_state.get('fg_scan_result')
if result is not None:
    rows = result['rows']
    broken = result['broken']
    checked = result['checked']
    discovered = result['discovered']
    st.success(f'Scanned {len(rows)} pages')
    a, b, c = st.columns(3)
    a.metric('Pages', len(rows))
    b.metric('Links checked', checked)
    c.metric('Link issues', len(broken))
    st.subheader('Page audit')
    st.dataframe(rows, use_container_width=True, hide_index=True)
    st.download_button('Download page audit CSV', to_csv(rows), 'filip_guard_pages.csv', 'text/csv')
    st.subheader('Internal link issues')
    st.subheader('AI Advisor - SEO Recommendations')
    st.caption('Current recommendations use fixed SEO rules. No AI model is connected; suggested text is a template for human review.')
    recommendations = analyze_pages(rows)
    st.dataframe(recommendations, use_container_width=True, hide_index=True)
    for page in rows:
        if "Missing meta description" in str(page.get("issues", "")):
            st.write(suggest_meta_description(page.get("title", "")))
    if broken:
        st.dataframe(broken, use_container_width=True, hide_index=True)
        st.download_button('Download link issues CSV', to_csv(broken), 'filip_guard_links.csv', 'text/csv')
        st.subheader('WordPress link replacement suggestions (read-only)')
        candidates = result['candidates']
        if candidates:
            st.dataframe(candidates, use_container_width=True, hide_index=True)
            st.caption('Candidates are reachable, but their relevance is not confirmed. Review before any change. No edits are made.')
        else:
            st.info('No verified WordPress replacement candidates found in the sampled public pages/posts.')
    else:
        st.info(f'No broken links found among {checked} checked (of {discovered} discovered). This does not guarantee all links work.')
    render_public_wordpress_audit(rows, result['start_url'])

st.caption('Beta: checks HTML SEO signals and internal links only. Not a complete SEO, performance or security audit. Scan sites you own or are authorized to audit.')
render_wordpress_autofix_ui()
render_autofix_sandbox()


render_monitoring()
