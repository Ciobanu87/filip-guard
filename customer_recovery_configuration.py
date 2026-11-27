"""Explicit opt-in only; existing retained key and state, no SMTP on construction."""
import os
from pathlib import Path
from runtime_state import require_existing_guard_state
from operator_secrets import configured_master_keys
from customer_recovery import AccountRecovery


def configured_account_recovery(auth):
    if os.environ.get('FG_ACCOUNT_RECOVERY_AUTHORIZED')!='1' or os.environ.get('FG_EMAIL_AUTHORIZED')!='1':return None
    require_existing_guard_state()
    if Path(auth.path).resolve()!=Path(os.environ['FG_CUSTOMER_AUTH_DB']).resolve():raise ValueError('Account database binding required')
    return AccountRecovery(auth,configured_master_keys(),key_id=os.environ['FG_GUARD_KEY_ID'],authorized=True)


def configured_account_dispatcher(monitor):
    if os.environ.get('FG_ACCOUNT_RECOVERY_AUTHORIZED')!='1' or os.environ.get('FG_EMAIL_AUTHORIZED')!='1':return None
    recovery=configured_account_recovery(monitor.auth)
    if recovery is None:return None
    from monitoring_email_configuration import configured_smtp_budget
    sender=configured_smtp_budget(monitor)
    class Dispatcher:
        def dispatch_once(self):return recovery.dispatch_once(sender)
    return Dispatcher()
