"""No code/password echo; all messages are generic; no automatic login after reset."""
from customer_recovery_configuration import configured_account_recovery


def render_account_recovery(ui,auth,*,service=None,clear_state=lambda:None):
    if auth is None:return
    try:service=service if service is not None else configured_account_recovery(auth)
    except Exception:return
    if service is None:return
    with ui.expander('Account verification and recovery',expanded=False):
        token=ui.session_state.get('fg_customer_session')
        if token:
            with ui.form('fg_customer_verify_request',clear_on_submit=True):
                address=ui.text_input('Recovery email address',max_chars=254)
                password=ui.text_input('Confirm account password',type='password')
                send=ui.form_submit_button('Request email verification code')
            if send:
                try:service.request_verification(token,password,address)
                except Exception:ui.warning('The account request could not be accepted. Check your details or try later.')
                else:ui.info('If eligible, a verification code has been queued. Codes expire in 15 minutes.')
        with ui.form('fg_customer_verify_confirm',clear_on_submit=True):
            verification=ui.text_input('Email verification code',type='password',max_chars=43)
            verify=ui.form_submit_button('Verify recovery email')
        if verify:
            try:service.confirm_verification(verification)
            except Exception:ui.warning('The code is invalid or expired.')
            else:ui.success('Recovery email verified. This does not sign you in.')
        with ui.form('fg_customer_recover_request',clear_on_submit=True):
            username=ui.text_input('Account username for recovery',max_chars=64)
            recover=ui.form_submit_button('Request password recovery code')
        if recover:
            try:service.request_recovery(username)
            except Exception:pass
            ui.info('If this account has a verified recovery address and is eligible, a code has been queued.')
        with ui.form('fg_customer_recover_confirm',clear_on_submit=True):
            code=ui.text_input('Password recovery code',type='password',max_chars=43)
            password=ui.text_input('New account password',type='password')
            confirmation=ui.text_input('Confirm new account password',type='password')
            reset=ui.form_submit_button('Reset account password')
        if reset:
            try:
                if password!=confirmation:raise ValueError('Mismatch')
                service.reset_password(code,password)
            except Exception:ui.warning('Password reset could not be completed. Check the code, password requirements and expiry.')
            else:
                clear_state();ui.success('Password reset. Sign in again; previous sessions were revoked.')
