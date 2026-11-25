"""Explicit operator configuration shared by UI and offline recovery tools.

Mounted private files remain the default. Streamlit-managed secrets are an
explicit opt-in; credentials stay in memory and never become local JSON files.
"""
import json
import os
from operator_secrets import private_file
from external_backup_store import S3BackupConfig,configured_s3_store


def configured_external_store(*, environ=None, managed_secrets=None):
    env=os.environ if environ is None else environ
    source=env.get('FG_GUARD_S3_SECRET_SOURCE','file')
    if source=='file':
        def credentials():
            data=json.loads(private_file(env['FG_GUARD_S3_CREDENTIALS_FILE'],8192))
            return (data['access_key_id'],data['secret_access_key']) if not data.get('session_token') else (
                data['access_key_id'],data['secret_access_key'],data['session_token'])
        config=S3BackupConfig(env['FG_GUARD_S3_ENDPOINT'],env['FG_GUARD_S3_BUCKET'],
            env.get('FG_GUARD_S3_REGION','us-east-1'))
    elif source=='streamlit':
        try:
            if managed_secrets is None:
                import streamlit as st
                managed_secrets=st.secrets
            data=managed_secrets['filip_guard_backup']
            config=S3BackupConfig(data['endpoint_url'],data['bucket'],data['region'])
            # Snapshot only explicitly named credentials; no ambient SDK lookup.
            values=(data['access_key_id'],data['secret_access_key'])
            if data.get('session_token'):values+= (data['session_token'],)
            if any(type(value) is not str or not value.strip() or len(value)>4096 for value in values):
                raise ValueError()
        except Exception:
            raise ValueError('Private managed backup settings unavailable or invalid') from None
        credentials=lambda:values
    else:
        raise ValueError('Unreviewed backup secret source')
    return configured_s3_store(config,credentials)
