"""Read-only bridge from public Scanner to existing owner-scoped Advisor.

No registration, storage bootstrap, WordPress credential access or repair path.
"""
from hashlib import sha256
import json
import os
from pathlib import Path

from contextual_advisor import configured_advisor, rule_result
from advisor_language import render_language
from monitoring_scan import target_url
from monitoring_configuration import configured_monitoring
from contextual_advisor_ui import render_advice


def owned_scan(directory, session, scan):
    principal = directory.auth.resolve(session)
    origin = 'https://' + target_url(scan['start_url'])[0]
    match = [site for site in directory.list_sites(session) if site['origin'] == origin]
    if len(match) != 1: raise PermissionError('Authorize this site in monitoring before model analysis')
    site_id = match[0]['site_id']
    directory._owned(session, site_id)
    rows, contexts = scan['rows'], scan.get('contexts', {})
    if type(rows) is not list or not 1 <= len(rows) <= 30 or type(contexts) is not dict:
        raise ValueError('Bounded public scan required')
    pages = set()
    for row in rows:
        page_origin = 'https://' + target_url(row['page'])[0]
        if page_origin != origin:
            raise PermissionError('Scan contains an unauthorized origin')
        pages.add(row['page'])
    if not set(contexts).issubset(pages): raise PermissionError('Context outside the authorized scan')
    digest = sha256(json.dumps([rows, contexts], sort_keys=True, ensure_ascii=True).encode()).hexdigest()
    return principal.customer_id + ':' + site_id, site_id, digest


def analyze_owned_scan(directory, session, scan, *, engine=None, language='en'):
    scope, site_id, _ = owned_scan(directory, session, scan)
    if engine is None:
        # A missing/deleted usage DB must not silently become a fresh allowance.
        path = os.environ.get('FG_AI_LEDGER_DB')
        if not path or not Path(path).is_file():
            raise ValueError('Existing shared AI usage ledger required; no new budget was created')
        engine = configured_advisor()
    if engine is None: raise ValueError('Model provider is not authorized/configured')
    return engine.analyze(scan['rows'], scan.get('contexts', {}), scope=scope,
        checkpoint=lambda: directory._owned(session, site_id), language=language)


def render_public_scan_advice(ui, scan, *, service=None, engine=None):
    fallback = rule_result(scan['rows'], scan.get('contexts', {}))
    session = ui.session_state.get('fg_customer_session')
    if not session:
        ui.caption('Public demo uses rules. Sign in and authorize the site for optional AI analysis.')
        render_advice(ui, fallback); return
    try:
        service = service if service is not None else configured_monitoring()
        if service is None: raise ValueError('Private account/site storage is not configured')
        scope, _, digest = owned_scan(service.directory, session, scan)
    except Exception:
        ui.info('AI analysis requires an active account and verified ownership of this scanned site. Configure private storage and authorize the site in monitoring.')
        render_advice(ui, fallback); return
    prefix = 'fg_customer_public_advisor_' + sha256((scope + digest).encode()).hexdigest()
    language = ui.selectbox('Advisor language', ['en', 'ro'], key=prefix+'_language')
    if ui.button('Analyze context with AI', key=prefix+'_analyze'):
        try:
            ui.session_state[prefix+'_result'] = analyze_owned_scan(service.directory, session, scan, engine=engine)
        except Exception:
            ui.session_state.pop(prefix+'_result', None)
            ui.warning('Model analysis could not start safely. Check the authorized provider, existing usage ledger and private configuration. No repair was performed.')
    # Ownership and session were checked above even when rendering previous results.
    result = ui.session_state.get(prefix+'_result', fallback)
    render_advice(ui, render_language(result, language))
