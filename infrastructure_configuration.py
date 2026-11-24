"""Explicit operator configuration shared by UI and offline recovery tools."""
import json
import os
from operator_secrets import private_file
from external_backup_store import S3BackupConfig,configured_s3_store


def configured_external_store():
    def credentials():
        data=json.loads(private_file(os.environ['FG_GUARD_S3_CREDENTIALS_FILE'],8192))
        return (data['access_key_id'],data['secret_access_key']) if not data.get('session_token') else (
            data['access_key_id'],data['secret_access_key'],data['session_token'])
    return configured_s3_store(S3BackupConfig(os.environ['FG_GUARD_S3_ENDPOINT'],os.environ['FG_GUARD_S3_BUCKET'],
        os.environ.get('FG_GUARD_S3_REGION','us-east-1')),credentials)
