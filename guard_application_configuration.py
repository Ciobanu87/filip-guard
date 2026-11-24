"""Operator-configured isolated test UI; no ambient or personal credentials.

Nothing is enabled by default. .test origins cannot enable customer production
sites. Tests inject their private ephemeral runtime and simulated object store.
"""
import json
import os
from pathlib import Path
from customer_auth import CustomerAuth
from customer_sites import CustomerSites
from external_backup_store import S3BackupConfig,configured_s3_store
from guard_application import GuardApplication
from monitoring_service import MonitoringService
from wordpress_rest_gateway import WordPressRESTGateway


def _private_file(path,limit):
    value=Path(path)
    if value.is_symlink() or not value.is_file() or value.stat().st_mode & 0o077 or value.stat().st_size>limit:
        raise ValueError('Private operator configuration required')
    return value.read_bytes()


def configured_guard_application():
    if os.environ.get('FG_GUARD_TEST_UI')!='1':return None
    names=('FG_CUSTOMER_AUTH_DB','FG_CUSTOMER_DATA_ROOT','FG_MONITOR_DB','FG_GUARD_TEST_ORIGINS',
           'FG_GUARD_MASTER_KEY_FILE','FG_GUARD_S3_CREDENTIALS_FILE','FG_GUARD_S3_ENDPOINT','FG_GUARD_S3_BUCKET')
    if not all(os.environ.get(name) for name in names):return None
    origins=json.loads(os.environ['FG_GUARD_TEST_ORIGINS'])
    if type(origins) is not list or not origins:raise ValueError('Explicit isolated test sites required')
    # Validate the immutable mutation allowlist before loading any secrets/SDK.
    from wordpress_execution_gate import _origin
    from urllib.parse import urlsplit
    if any(type(origin) is not str or not urlsplit('https://'+_origin(origin)).hostname.endswith('.test') for origin in origins):
        raise ValueError('Only isolated .test sites may be enabled')
    key_id=os.environ.get('FG_GUARD_KEY_ID','test-v1')
    def master_keys(requested):
        if requested!=key_id:raise PermissionError('Requested key version unavailable')
        key=_private_file(os.environ['FG_GUARD_MASTER_KEY_FILE'],32)
        if len(key)!=32:raise PermissionError('Externally retained 256-bit key required')
        return key
    def storage_credentials():
        data=json.loads(_private_file(os.environ['FG_GUARD_S3_CREDENTIALS_FILE'],8192))
        return (data['access_key_id'],data['secret_access_key']) if not data.get('session_token') else (
            data['access_key_id'],data['secret_access_key'],data['session_token'])
    store=configured_s3_store(S3BackupConfig(os.environ['FG_GUARD_S3_ENDPOINT'],os.environ['FG_GUARD_S3_BUCKET']),storage_credentials)
    auth=CustomerAuth(os.environ['FG_CUSTOMER_AUTH_DB'])
    sites=CustomerSites(auth,os.environ['FG_CUSTOMER_DATA_ROOT'],master_keys,active_key_id=key_id,
                        object_store=store,gateway_factory=WordPressRESTGateway)
    monitor=MonitoringService(sites,os.environ['FG_MONITOR_DB'])
    return GuardApplication(sites,monitor,authorized_test_origins=origins,
                            allow_registration=os.environ.get('FG_CUSTOMER_REGISTRATION')=='1')
