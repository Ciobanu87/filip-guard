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
from ai_advisor import analyze_pages
st.set_page_config(page_title='FILIP GUARD | Website Health & SEO', page_icon='🛡️', layout='centered')
st.title('🛡️ FILIP GUARD')
st.caption('Website Health & SEO • Beta')
st.write('Audit up to 30 public pages, find basic SEO issues and check internal links.')

HEADERS = {'User-Agent': 'FilipGuardAudit/0.1 (+website-health-check)'}
MAX_BYTES = 1_500_000


def public_host(host):
    if not host or host.lower() == 'localhost':
        return False
    try:
        answers = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
        return bool(answers) and all(ipaddress.ip_address(a[4][0]).is_global for a in answers)
    except (OSError, ValueError):
        return False


def validate_url(value, host=None):
    p = urlparse(value)
    if p.scheme not in ('http', 'https') or not p.hostname or p.username or p.password or p.port not in (None, 80, 443):
        raise ValueError('Only public HTTP/HTTPS websites are supported.')
    if host and p.hostname.lower() != host:
        raise ValueError('External redirect blocked.')
    if not public_host(p.hostname):
        raise ValueError('Private or unreachable host blocked.')
    return value


def fetch(url, host, method='GET'):
    # No automatic redirects: validate each destination, including DNS resolution.
    current = url
    for _ in range(5):
        validate_url(current, host)
        r = requests.request(method, current, headers=HEADERS, timeout=(4, 8), allow_redirects=False, stream=True)
        if r.status_code in (301, 302, 303, 307, 308) and r.headers.get('Location'):
            next_url = urljoin(current, r.headers['Location'])
            r.close()
            current = next_url
            continue
        if method == 'HEAD':
            status = r.status_code
            r.close()
            return status, current, ''
        if 'text/html' not in r.headers.get('Content-Type', '').lower():
            r.close()
            return r.status_code, current, ''
        data = bytearray()
        for chunk in r.iter_content(chunk_size=16384):
            data.extend(chunk)
            if len(data) > MAX_BYTES:
                r.close()
                raise ValueError('Page too large')
        encoding = r.encoding or 'utf-8'
        result = bytes(data).decode(encoding, errors='replace')
        status = r.status_code
        r.close()
        return status, current, result
    raise ValueError('Too many redirects')


def normalize_link(base, href, host):
    if not href or href.startswith(('#', 'mailto:', 'tel:', 'javascript:', 'data:')):
        return None
    link = urldefrag(urljoin(base, href.strip()))[0]
    p = urlparse(link)
    if p.scheme not in ('http', 'https') or p.hostname != host:
        return None
    return link


def scan(start, limit):
    if not urlparse(start).scheme:
        start = 'https://' + start
    validate_url(start)
    host = urlparse(start).hostname.lower()
    queue = deque([start])
    seen = set()
    rows = []
    link_sources = {}
    while queue and len(rows) < limit:
        url = queue.popleft()
        if url in seen:
            continue
        seen.add(url)
        try:
            began = time.monotonic()
            status, final, html = fetch(url, host)
            duration = round(time.monotonic() - began, 2)
            if not html:
                rows.append({'page': url, 'http_status': status, 'response_seconds': duration, 'title': '', 'meta_description': '', 'h1_count': 0, 'images_missing_alt': 0, 'issues': 'Non-HTML or empty page'})
                continue
            soup = BeautifulSoup(html, 'html.parser')
            title = soup.title.get_text(' ', strip=True) if soup.title else ''
            desc_tag = soup.find('meta', attrs={'name': lambda v: isinstance(v, str) and v.lower() == 'description'})
            desc = (desc_tag.get('content') or '').strip() if desc_tag else ''
            h1_count = len(soup.find_all('h1'))
            no_alt = sum(1 for img in soup.find_all('img') if not (img.get('alt') or '').strip())
            issues = []
            if status >= 400: issues.append('HTTP error')
            if not title: issues.append('Missing title')
            if not desc: issues.append('Missing meta description')
            if h1_count != 1: issues.append('H1 count not 1')
            if no_alt: issues.append('Images missing ALT')
            rows.append({'page': url, 'http_status': status, 'response_seconds': duration, 'title': title, 'meta_description': desc, 'h1_count': h1_count, 'images_missing_alt': no_alt, 'issues': '; '.join(issues)})
            for a in soup.find_all('a', href=True):
                link = normalize_link(final, a['href'], host)
                if link:
                    link_sources.setdefault(link, set()).add(url)
                    if link not in seen and link not in queue and len(seen) + len(queue) < limit * 4:
                        queue.append(link)
        except (requests.RequestException, ValueError, UnicodeError) as exc:
            rows.append({'page': url, 'http_status': 'ERROR', 'response_seconds': '', 'title': '', 'meta_description': '', 'h1_count': '', 'images_missing_alt': '', 'issues': str(exc)[:120]})
    broken = []
    # Check a bounded number of distinct internal links, regardless of crawl page count.
    for link, sources in list(link_sources.items())[:100]:
        try:
            code, _, _ = fetch(link, host, 'HEAD')
            if code in (403, 405, 501):
                code, _, _ = fetch(link, host, 'GET')
            if code >= 400:
                broken.append({'link': link, 'status': code, 'found_on': ', '.join(sorted(sources)[:3])})
        except (requests.RequestException, ValueError) as exc:
            broken.append({'link': link, 'status': 'Check failed', 'found_on': ', '.join(sorted(sources)[:3])})
    return rows, broken, min(len(link_sources), 100), len(link_sources)


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
    if not url.strip():
        st.warning('Enter a website URL.')
    else:
        try:
            with st.spinner('Scanning public pages. This may take a little while…'):
                rows, broken, checked, discovered = scan(url.strip(), pages)
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
            recommendations = analyze_pages(rows)
            st.dataframe(recommendations, use_container_width=True, hide_index=True)
            if broken:
                st.dataframe(broken, use_container_width=True, hide_index=True)
                st.download_button('Download link issues CSV', to_csv(broken), 'filip_guard_links.csv', 'text/csv')
            else:
                st.info(f'No broken links found among {checked} checked (of {discovered} discovered). This does not guarantee all links work.')
        except (ValueError, requests.RequestException) as exc:
            st.error(f'Could not scan: {exc}')

st.caption('Beta: checks HTML SEO signals and internal links only. Not a complete SEO, performance or security audit. Scan sites you own or are authorized to audit.')
