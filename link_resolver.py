"""Read-only candidate matcher for broken WordPress links.

Accepts public WordPress REST API posts/pages (already retrieved by an authorized
scanner). It never connects to WordPress or modifies content. Suggestions are
unverified until the scanner checks the candidate URL and a person reviews it.
"""
from difflib import SequenceMatcher
from html import unescape
from urllib.parse import unquote, urlparse


def _slug(url):
    path = urlparse(url).path.rstrip('/')
    return unquote(path.rsplit('/', 1)[-1]).lower().replace('-', ' ').replace('_', ' ')


def _text(value):
    if isinstance(value, dict):
        value = value.get('rendered', '')
    if not isinstance(value, str):
        return ''
    return unescape(value).replace('<', ' ').replace('>', ' ').strip().lower()


def suggest_replacements(broken_url, wordpress_items, limit=3, threshold=0.45):
    """Return ranked *unverified* candidates from WP REST API posts/pages.

    wordpress_items: list of WP /wp-json/wp/v2/posts or pages objects.
    Only links on the same hostname as broken_url are considered.
    """
    parsed = urlparse(broken_url)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname:
        return []
    target = _slug(broken_url)
    if not target:
        return []
    results = []
    for item in wordpress_items:
        if not isinstance(item, dict) or item.get('status', 'publish') != 'publish':
            continue
        candidate = item.get('link', '')
        if not isinstance(candidate, str):
            continue
        p = urlparse(candidate)
        if p.scheme not in ('http', 'https') or p.hostname != parsed.hostname or candidate == broken_url:
            continue
        slug = _text(item.get('slug')) or _slug(candidate)
        title = _text(item.get('title'))
        score = max(SequenceMatcher(None, target, slug.replace('-', ' ')).ratio(),
                    SequenceMatcher(None, target, title).ratio() if title else 0)
        if score >= threshold:
            results.append({'broken_url': broken_url, 'candidate_url': candidate,
                            'title': title, 'similarity': round(score, 3),
                            'verified': False, 'requires_review': True})
    results.sort(key=lambda r: (-r['similarity'], r['candidate_url']))
    return results[:max(0, min(int(limit), 10))]
