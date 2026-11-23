"""Streamlit integration for the isolated, synthetic AutoFix fixture only.

Never accepts a site URL or credentials and never constructs a network gateway.
The fixture has no connection to a real WordPress installation.
"""
from pathlib import Path
import secrets
import tempfile

from backup import BackupManager
from wordpress_autofix_engine import AutoFixEngine
from wordpress_local_fixture import LocalWordPressFixture


_SITE = 'https://filip-guard.invalid'


def render_autofix_sandbox(st_module=None):
    if st_module is None:
        import streamlit as st_module
    ui = st_module
    with ui.expander('AutoFix — isolated local test', expanded=False):
        ui.caption('Synthetic content only. No WordPress connection, credentials or real website changes. '
                   'This test does not validate compatibility with a real WordPress server.')
        if not ui.checkbox('Open isolated AutoFix test', key='fg_autofix_open'):
            return
        state_key = 'fg_autofix_local_context'
        if state_key not in ui.session_state:
            directory = tempfile.TemporaryDirectory(prefix='fg-autofix-fixture-')
            root = Path(directory.name)
            gateway = LocalWordPressFixture(root / 'fixture.sqlite')
            gateway.seed(_SITE, 'post', 1, '<p>Original test content.</p>\n', user_id=1)
            backups = BackupManager(root / 'backups.sqlite')
            ui.session_state[state_key] = {
                'directory': directory, 'gateway': gateway,
                'engine': AutoFixEngine(root / 'repairs.sqlite', backups, gateway),
                'session_id': secrets.token_urlsafe(32), 'plan_id': None, 'result': None,
            }
        context = ui.session_state[state_key]
        engine, gateway = context['engine'], context['gateway']
        session = dict(user_id=1, session_id=context['session_id'])
        snapshot = gateway.read_authorized(_SITE, 'post', 1, 1)
        ui.write('Current local test content')
        ui.code(snapshot.content, language='html')
        proposed = ui.text_area('Proposed test content', '<p>Updated test content.</p>\n',
                                key='fg_autofix_proposed')
        if ui.button('Prepare local repair', key='fg_autofix_prepare'):
            try:
                plan = engine.propose(site_url=_SITE, resource_type='post', resource_id=1,
                                      proposed_content=proposed, **session)
                context['plan_id'], context['result'] = plan['plan_id'], None
            except Exception:
                ui.error('Could not prepare the local repair. Check the proposed content and try again.')
        plan_id = context['plan_id']
        if plan_id and context['result'] is None:
            try:
                review = engine.review(plan_id, **session)
                ui.write('Exact change for this repair')
                ui.code(review['diff'], language='diff')
                confirmed = ui.checkbox('I approve this exact local test change',
                                        key='fg_autofix_confirm_' + plan_id)
                if ui.button('Apply approved local repair', key='fg_autofix_apply_' + plan_id,
                             disabled=not confirmed):
                    token = engine.approve(plan_id, confirmed=confirmed, **session)
                    context['result'] = engine.apply(plan_id, token, **session)
                    ui.rerun()
            except Exception:
                ui.error('This local proposal is invalid, stale or expired. Prepare and review a fresh repair.')
        if context['result'] is not None:
            result = context['result']
            if result['status'] == 'applied':
                ui.success('Local repair applied and verified. No real website was changed.')
            else:
                ui.warning('Local repair status: ' + result['status'])
            ui.caption('Verified backup scope: affected content only. '
                       'The synthetic test files are temporary; this is not configured production storage.')
            ui.json(result)
