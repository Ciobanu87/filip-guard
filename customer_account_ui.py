"""Customer account UI; no WordPress login or live repair controls are enabled."""
import os
from customer_auth import CustomerAuth, AuthenticationError


def _clear_customer_state(ui):
    for key in list(ui.session_state):
        if str(key).startswith('fg_customer_'):
            del ui.session_state[key]


def render_customer_account(st_module=None, *, auth=None, allow_registration=None):
    if st_module is None:
        import streamlit as st_module
    ui = st_module
    if auth is None:
        database = os.environ.get('FG_CUSTOMER_AUTH_DB')
        if database:
            auth = CustomerAuth(database)
    if allow_registration is None:
        allow_registration = os.environ.get('FG_CUSTOMER_REGISTRATION') == '1'
    with ui.expander('Customer account', expanded=False):
        if auth is None:
            ui.info('Customer sign-in is not enabled for this deployment.')
            return None
        token = ui.session_state.get('fg_customer_session')
        if token:
            try:
                principal = auth.resolve(token)
            except AuthenticationError:
                _clear_customer_state(ui)
                ui.warning('Your session has expired. Sign in again.')
            else:
                ui.write('Signed in as ' + principal.username)
                if ui.button('Sign out', key='fg_account_logout'):
                    auth.logout(token)
                    _clear_customer_state(ui)
                    ui.rerun()
                ui.caption('WordPress AutoFix remains unavailable for customer sites.')
                return principal
        registering = allow_registration and ui.checkbox('Create an account', key='fg_account_register')
        with ui.form('fg_account_login', clear_on_submit=True):
            username = ui.text_input('Account username', max_chars=64)
            password = ui.text_input('Account password', type='password', max_chars=256)
            submitted = ui.form_submit_button('Create account' if registering else 'Sign in')
        if submitted:
            try:
                if registering:
                    auth.register(username, password)
                session = auth.login(username, password)
            except AuthenticationError:
                ui.error('Could not sign in or create this account. Check your details or try again later.')
            else:
                _clear_customer_state(ui)
                ui.session_state['fg_customer_session'] = session
                ui.rerun()
        return None
