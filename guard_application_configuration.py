"""Operator-configured isolated test UI; no ambient or personal credentials.

Nothing is enabled by default. .test origins cannot enable customer production
sites. Tests inject their private ephemeral runtime and simulated object store.
"""
import json
import os
from operator_secrets import private_file as _private_file,configured_master_keys
from customer_auth import CustomerAuth
from customer_sites import CustomerSites
from external_backup_store import S3BackupConfig,configured_s3_store
from guard_application import GuardApplication
from monitoring_service import MonitoringService
from wordpress_rest_gateway import WordPressRESTGateway


def configured_guard_application():
    if os.environ.get('FG_GUARD_TEST_UI')!='1':return None
    names=('FG_CUSTOMER_AUTH_DB','FG_CUSTOMER_DATA_ROOT','FG_MONITOR_DB','FG_GUARD_TEST_ORIGINS',
           'FG_GUARD_S3_CREDENTIALS_FILE','FG_GUARD_S3_ENDPOINT','FG_GUARD_S3_BUCKET')
    if not all(os.environ.get(name) for name in names):return None
    if not (os.environ.get('FG_GUARD_KEY_DIRECTORY') or os.environ.get('FG_GUARD_MASTER_KEY_FILE')):return None
    origins=json.loads(os.environ['FG_GUARD_TEST_ORIGINS'])
    if type(origins) is not list or not origins:raise ValueError('Explicit isolated test sites required')
    # Validate the immutable mutation allowlist before loading any secrets/SDK.
    from wordpress_execution_gate import _origin
    from urllib.parse import urlsplit
    if any(type(origin) is not str or not urlsplit('https://'+_origin(origin)).hostname.endswith('.test') for origin in origins):
        raise ValueError('Only isolated .test sites may be enabled')
    key_id=os.environ.get('FG_GUARD_KEY_ID','test-v1')
    master_keys=configured_master_keys()
    def storage_credentials():
        data=json.loads(_private_file(os.environ['FG_GUARD_S3_CREDENTIALS_FILE'],8192))
        return (data['access_key_id'],data['secret_access_key']) if not data.get('session_token') else (
            data['access_key_id'],data['secret_access_key'],data['session_token'])
    store=configured_s3_store(S3BackupConfig(os.environ['FG_GUARD_S3_ENDPOINT'],os.environ['FG_GUARD_S3_BUCKET'],os.environ.get('FG_GUARD_S3_REGION','us-east-1')),storage_credentials)
    auth=CustomerAuth(os.environ['FG_CUSTOMER_AUTH_DB'])
    sites=CustomerSites(auth,os.environ['FG_CUSTOMER_DATA_ROOT'],master_keys,active_key_id=key_id,
                        object_store=store,gateway_factory=WordPressRESTGateway)
    monitor=MonitoringService(sites,os.environ['FG_MONITOR_DB'])
    return GuardApplication(sites,monitor,authorized_test_origins=origins,
                            allow_registration=os.environ.get('FG_CUSTOMER_REGISTRATION')=='1')
