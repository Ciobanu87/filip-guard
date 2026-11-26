import json
import unittest
from operations_oracle_b2_mount import payload


class PrivateB2MountTests(unittest.TestCase):
    def env(self):
        return {'FG_B2_ENDPOINT': 'https://s3.eu-central-003.backblazeb2.com',
                'FG_B2_BUCKET': 'synthetic-test-only', 'FG_B2_KEY_ID': 'synthetic-id',
                'FG_B2_APPLICATION_KEY': 'synthetic-private-key-not-live'}

    def test_private_values_stay_in_data_payload_with_explicit_region_not_command_text(self):
        data = json.loads(payload(self.env(), 'a' * 64))
        self.assertEqual(data['region'], 'eu-central-003')
        self.assertEqual(data['credentials']['secret_access_key'], self.env()['FG_B2_APPLICATION_KEY'])
        self.assertNotIn('master_key', data)

    def test_invalid_or_credential_bearing_redirect_capable_endpoints_are_rejected(self):
        for url in ('http://s3.eu-central-003.backblazeb2.com', 'https://user:pass@s3.eu-central-003.backblazeb2.com',
                    'https://127.0.0.1', 'https://example.com', 'https://s3.eu-central-003.backblazeb2.com/path',
                    'https://s3.eu-central-003.backblazeb2.com?token=secret'):
            with self.assertRaises(ValueError): payload({**self.env(), 'FG_B2_ENDPOINT': url}, 'a' * 64)

    def test_env_injection_missing_or_oversized_private_values_fail_closed(self):
        for change in ({'FG_B2_BUCKET': 'bucket\nFG_STATE_BACKUP_AUTHORIZED=1'},
                       {'FG_B2_APPLICATION_KEY': ''}, {'FG_B2_APPLICATION_KEY': 'x' * 4097},
                       {'FG_B2_KEY_ID': 'id\nextra'}):
            with self.assertRaises(ValueError): payload({**self.env(), **change}, 'a' * 64)


if __name__ == '__main__': unittest.main()
