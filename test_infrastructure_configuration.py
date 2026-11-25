import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from infrastructure_configuration import configured_external_store


class ManagedBackupConfigurationTests(unittest.TestCase):
    def managed(self):
        return {'filip_guard_backup':{'endpoint_url':'https://s3.eu-central-003.backblazeb2.com',
            'bucket':'synthetic-private-backup-test','region':'eu-central-003',
            'access_key_id':'synthetic-key-id','secret_access_key':'synthetic-secret'}}
    def test_explicit_managed_secrets_reach_existing_adapter_without_file_or_network(self):
        with patch('infrastructure_configuration.configured_s3_store') as adapter,patch('infrastructure_configuration.private_file') as disk:
            result=configured_external_store(environ={'FG_GUARD_S3_SECRET_SOURCE':'streamlit'},managed_secrets=self.managed())
            config,provider=adapter.call_args.args
            self.assertEqual(config.region,'eu-central-003')
            self.assertEqual(provider(),('synthetic-key-id','synthetic-secret'))
            self.assertEqual(result,adapter.return_value);disk.assert_not_called()
    def test_file_configuration_remains_default(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'keys.json';path.write_text(json.dumps({'access_key_id':'synthetic-id','secret_access_key':'synthetic-secret'}));path.chmod(0o600)
            env={'FG_GUARD_S3_CREDENTIALS_FILE':str(path),'FG_GUARD_S3_ENDPOINT':'https://s3.test','FG_GUARD_S3_BUCKET':'test-backup'}
            with patch('infrastructure_configuration.configured_s3_store') as adapter:
                configured_external_store(environ=env)
                self.assertEqual(adapter.call_args.args[1](),('synthetic-id','synthetic-secret'))
    def test_missing_or_blank_secret_is_sanitized_before_adapter(self):
        for data in ({}, {'filip_guard_backup':{}}, self.managed()):
            if data.get('filip_guard_backup',{}).get('secret_access_key'):data['filip_guard_backup']['secret_access_key']=' '
            with patch('infrastructure_configuration.configured_s3_store') as adapter:
                with self.assertRaisesRegex(ValueError,'Private managed backup settings'):
                    configured_external_store(environ={'FG_GUARD_S3_SECRET_SOURCE':'streamlit'},managed_secrets=data)
                adapter.assert_not_called()
    def test_managed_settings_not_used_without_explicit_source(self):
        with self.assertRaises(KeyError):configured_external_store(environ={},managed_secrets=self.managed())
        with self.assertRaises(ValueError):configured_external_store(environ={'FG_GUARD_S3_SECRET_SOURCE':'unknown'},managed_secrets=self.managed())
    def test_existing_adapter_still_rejects_insecure_endpoint(self):
        data=self.managed();data['filip_guard_backup']['endpoint_url']='http://s3.test'
        with self.assertRaises(ValueError):configured_external_store(environ={'FG_GUARD_S3_SECRET_SOURCE':'streamlit'},managed_secrets=data)
