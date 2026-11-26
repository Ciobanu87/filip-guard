import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from deployment.oracle_account_access_inspect import inspect, read_home, result
from operations_oracle_account_access import validate


class ExistingAccountAccessTests(unittest.TestCase):
    def test_no_preinstalled_tools_returns_without_authentication_network_or_install(self):
        with patch('deployment.oracle_account_access_inspect.importlib.util.find_spec', return_value=None), \
             patch('deployment.oracle_account_access_inspect.shutil.which', return_value=None), \
             patch('deployment.oracle_account_access_inspect.subprocess.run') as run, \
             patch('deployment.oracle_account_access_inspect.urllib.request.build_opener') as network:
            report = inspect()
        run.assert_not_called(); network.assert_not_called()
        self.assertEqual(validate(report)['status'], 'no-existing-account-tooling')
        self.assertFalse(report['cumulative_usage_verified'])

    def test_complete_home_region_response_does_not_prove_resource_or_billing_totals(self):
        rows = [{'region-name': 'eu-frankfurt-1', 'is-home-region': True}]
        report = validate(read_home(rows, True, result()))
        self.assertTrue(report['home_region_frankfurt_verified'])
        self.assertTrue(report['existing_identity_read_authorized'])
        self.assertFalse(report['account_resource_inventory_verified'])
        self.assertFalse(report['cumulative_usage_verified'])

    def test_pagination_missing_or_multiple_home_rows_never_pass(self):
        for rows, complete in (([], True), ([{'region-name': 'eu-frankfurt-1', 'is-home-region': True}], False),
                               ([{'region-name': 'eu-frankfurt-1', 'is-home-region': False}], True),
                               ([{'region-name': 'eu-frankfurt-1', 'is-home-region': True}] * 2, True)):
            report = read_home(rows, complete, result())
            self.assertFalse(report['home_region_frankfurt_verified'])
            self.assertFalse(report['existing_identity_read_authorized'])

    def test_other_home_region_is_reported_without_raw_identifiers(self):
        report = validate(read_home([{'region-name': 'us-ashburn-1', 'is-home-region': True}], True, result()))
        self.assertFalse(report['home_region_frankfurt_verified'])
        self.assertNotIn('us-ashburn-1', json.dumps(report))

    def test_cli_failure_is_sanitized_and_does_not_fall_back_to_user_keys(self):
        import io
        metadata = io.BytesIO(json.dumps({'compartmentId': 'ocid1.tenancy.oc1.synthetic-test-only'}).encode())
        with patch('deployment.oracle_account_access_inspect.importlib.util.find_spec', return_value=None), \
             patch('deployment.oracle_account_access_inspect.shutil.which', return_value='/usr/bin/oci'), \
             patch('deployment.oracle_account_access_inspect.urllib.request.build_opener') as network, \
             patch('deployment.oracle_account_access_inspect.subprocess.run', return_value=SimpleNamespace(
                 returncode=1, stdout='', stderr='sensitive provider failure text')) as run:
            network.return_value.open.return_value = metadata
            report = validate(inspect())
        self.assertEqual(report['status'], 'existing-identity-read-unavailable')
        self.assertNotIn('sensitive', json.dumps(report))
        args = run.call_args.args[0]
        self.assertIn('instance_principal', args)
        self.assertIn('/dev/null', args)
        self.assertFalse(report['iam_permissions_changed'])
        self.assertNotIn('OCI_CLI_KEY_FILE', run.call_args.kwargs['env'])

    def test_forged_or_credential_bearing_reports_are_rejected(self):
        for change in ({'private_key': 'do-not-log'}, {'cumulative_usage_verified': True},
                       {'account_resource_inventory_verified': True}, {'server_modified': True},
                       {'iam_permissions_changed': True}, {'region_subscription_count': True},
                       {'groq_calls': 1}, {'status': 'raw-provider-secret'}):
            with self.assertRaises(ValueError): validate({**result(), **change})


if __name__ == '__main__': unittest.main()
