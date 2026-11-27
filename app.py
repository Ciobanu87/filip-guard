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
from contextual_advisor import rule_result
from contextual_advisor_ui import render_advice
from public_scan_advisor import render_public_scan_advice
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


from public_scan_workflow import run_public_scan, public_wordpress_items as wordpress_public_items, verified_wordpress_suggestions


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
                result=run_public_scan(url.strip(),pages)
            result['candidates']=verified_wordpress_suggestions(result['broken']) if result['broken'] else []
            st.session_state['fg_scan_result']=result
        except (ValueError, requests.RequestException):
            st.error('The HTTPS scan could not be completed. Check the public URL and try again after reviewing the failure.')

result = st.session_state.get('fg_scan_result')
if result is not None:
    rows = result['rows']
    broken = result['broken']
    checked = result['checked']
    discovered = result['discovered']
    st.success(f'Scanned {len(rows)} pages')
    if result.get('complete') is False:
        st.warning('This scan is incomplete. Request/time limits or blocked responses may leave issues unverified.')
    a, b, c = st.columns(3)
    a.metric('Pages', len(rows))
    b.metric('Links checked', checked)
    c.metric('Link issues', len(broken))
    st.subheader('Page audit')
    st.dataframe(rows, use_container_width=True, hide_index=True)
    st.download_button('Download page audit CSV', to_csv(rows), 'filip_guard_pages.csv', 'text/csv')
    st.subheader('Internal link issues')
    st.subheader('AI Advisor - SEO Recommendations')
    render_public_scan_advice(st,result)
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
