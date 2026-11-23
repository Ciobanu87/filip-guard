"""Trusted deployment paths only. No WordPress, SMTP or object-store secrets."""
import os
from pathlib import Path
from customer_auth import CustomerAuth
from customer_sites import CustomerSites
from monitoring_service import MonitoringService


def configured_monitoring():
    account_db=os.environ.get('FG_CUSTOMER_AUTH_DB')
    site_root=os.environ.get('FG_CUSTOMER_DATA_ROOT')
    monitor_db=os.environ.get('FG_MONITOR_DB')
    if not all((account_db,site_root,monitor_db)):return None
    if not Path(account_db).is_file() or not (Path(site_root)/'sites.sqlite').is_file():
        raise ValueError('Existing customer/site storage is required for monitoring')
    auth=CustomerAuth(account_db)
    # Monitoring needs ownership metadata only; credential decryption and writes stay disabled.
    directory=CustomerSites(auth,site_root,master_keys=None,gateway_factory=None)
    return MonitoringService(directory,monitor_db)
