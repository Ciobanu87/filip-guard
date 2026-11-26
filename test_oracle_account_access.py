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




class CoreAllocationTests(unittest.TestCase):
    def response(self, rows, next_page=None):
        return SimpleNamespace(data=rows, has_next_page=next_page is not None, next_page=next_page)

    def clients(self):
        from unittest.mock import Mock
        identity, compute, block = Mock(), Mock(), Mock()
        identity.list_region_subscriptions.return_value = self.response([
            SimpleNamespace(is_home_region=True, region_name='eu-frankfurt-1')])
        identity.list_compartments.return_value = self.response([])
        identity.list_availability_domains.return_value = self.response([SimpleNamespace(name='synthetic-domain')])
        compute.list_instances.return_value = self.response([
            SimpleNamespace(lifecycle_state='RUNNING', shape='VM.Standard.A1.Flex',
                            shape_config=SimpleNamespace(ocpus=1, memory_in_gbs=6))])
        block.list_boot_volumes.return_value = self.response([SimpleNamespace(lifecycle_state='AVAILABLE', size_in_gbs=47)])
        for method in ('list_volumes', 'list_boot_volume_backups', 'list_volume_backups'):
            getattr(block, method).return_value = self.response([])
        return identity, compute, block

    def test_complete_current_allocation_still_does_not_claim_historical_or_all_service_costs(self):
        from deployment.oracle_resource_inspect import collect
        from operations_oracle_resources import validate
        report = validate(collect(*self.clients(), 'synthetic-tenancy'))
        self.assertTrue(report['core_allocation_inventory_verified'])
        self.assertEqual((report['a1_instances'], report['a1_ocpus'], report['a1_memory_gib']), (1, 1, 6))
        self.assertEqual(report['boot_volume_gib'], 47)
        self.assertFalse(report['historical_usage_verified']); self.assertFalse(report['all_service_costs_verified'])
        self.assertNotIn('synthetic-tenancy', json.dumps(report))

    def test_permission_denial_stops_without_raw_error_or_false_partial_totals(self):
        from deployment.oracle_resource_inspect import collect
        identity, compute, block = self.clients()
        block.list_volumes.side_effect = RuntimeError('sensitive service request identifier')
        report = collect(identity, compute, block, 'synthetic-tenancy')
        self.assertEqual(report['blocked_step'], 'block-volume-list')
        self.assertFalse(report['core_allocation_inventory_verified'])
        self.assertEqual(report['boot_volume_gib'], 0)
        self.assertEqual(report['a1_instances'], 0)
        block.list_boot_volume_backups.assert_not_called()
        self.assertNotIn('sensitive', json.dumps(report))

    def test_missing_compartment_rights_never_fall_back_to_root_only_visibility(self):
        from deployment.oracle_resource_inspect import collect
        identity, compute, block = self.clients()
        identity.list_compartments.side_effect = PermissionError('denied')
        report = collect(identity, compute, block, 'synthetic-tenancy')
        self.assertEqual(report['blocked_step'], 'compartment-list')
        compute.list_instances.assert_not_called(); block.list_volumes.assert_not_called()

    def test_pagination_bound_or_additional_region_blocks_complete_claim(self):
        from deployment.oracle_resource_inspect import collect
        for multiple_regions in (False, True):
            identity, compute, block = self.clients()
            if multiple_regions:
                identity.list_region_subscriptions.return_value = self.response([
                    SimpleNamespace(is_home_region=True, region_name='eu-frankfurt-1'),
                    SimpleNamespace(is_home_region=False, region_name='us-ashburn-1')])
            else:
                identity.list_compartments.return_value = self.response([], next_page='continued')
            report = collect(identity, compute, block, 'synthetic-tenancy')
            self.assertFalse(report['core_allocation_inventory_verified'])
            compute.list_instances.assert_not_called()

    def test_stopped_and_terminating_instances_remain_conservatively_counted(self):
        from deployment.oracle_resource_inspect import collect
        identity, compute, block = self.clients()
        compute.list_instances.return_value = self.response([
            SimpleNamespace(lifecycle_state=state, shape='VM.Standard.A1.Flex',
                            shape_config=SimpleNamespace(ocpus=1, memory_in_gbs=6))
            for state in ('RUNNING', 'STOPPED', 'TERMINATING', 'TERMINATED')])
        report = collect(identity, compute, block, 'synthetic-tenancy')
        self.assertEqual(report['a1_instances'], 3)
        self.assertEqual(report['a1_ocpus'], 3)

    def test_invalid_aggregate_or_scope_cannot_be_reported_as_verified(self):
        from deployment.oracle_resource_inspect import blank
        from operations_oracle_resources import validate
        for change in ({'core_allocation_inventory_verified': True}, {'a1_instances': True},
                       {'historical_usage_verified': True}, {'iam_permissions_changed': True},
                       {'a1_ocpus': float('nan')}, {'account_private_key': 'never-print'},
                       {'scope': 'all-service-account-billing-verified'}):
            with self.assertRaises(ValueError): validate({**blank(), **change})

    def test_api_refusal_status_is_retained_without_sensitive_service_text(self):
        from deployment.oracle_resource_inspect import collect
        identity, compute, block = self.clients()
        failure = RuntimeError('sensitive request-id and service message')
        failure.status = 404
        compute.list_instances.side_effect = failure
        report = collect(identity, compute, block, 'synthetic-tenancy')
        self.assertEqual(report['api_http_status'], 404)
        self.assertEqual(report['blocked_step'], 'instance-list')
        self.assertNotIn('sensitive', json.dumps(report))


if __name__ == '__main__': unittest.main()
