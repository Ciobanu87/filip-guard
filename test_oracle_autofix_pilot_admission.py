"""Offline admission checks only; never connect to Oracle or providers."""
import unittest
from operations_oracle_autofix_pilot import assess


class PilotAdmissionTests(unittest.TestCase):
    def report(self):
        return dict(schema=1,logical_cpus=1,total_memory_mib=5642,docker_available=False,podman_available=False,arm64=True,shape_a1=True,imds_ocpus=1,imds_memory_gib=6,
            frankfurt_home_instance=True,visible_block_devices_gib=47,php_available=True,
            php_version='8.3.1',php_mysqli=True,sql_server_available=True,sql_initializer_available=True,
            existing_python_available=True,all_guard_units_inactive=True,private_scratch_free_bytes=9*1024**3,
            available_memory_mib=4096,server_modified=False,global_installations=0,public_listeners_created=0,
            groq_calls=0,smtp_messages=0,b2_calls=0)
    def test_missing_dependencies_hold_without_pretending_pilot_ran(self):
        report=self.report();report.update(php_available=False,php_version=None,php_mysqli=False,sql_server_available=False,sql_initializer_available=False)
        result=assess(report)
        self.assertEqual(result['status'],'pilot-held');self.assertFalse(result['pilot_executed'])
        self.assertTrue(result['allocation_within_current_free_limits'])
        self.assertIn('PHP 8.3',result['missing_dependencies'])
    def test_missing_or_changed_allocation_cannot_admit(self):
        for change in ({'imds_ocpus':None},{'imds_memory_gib':12},{'visible_block_devices_gib':201},{'visible_block_devices_gib':0},{'frankfurt_home_instance':False}):
            result=assess(self.report()|change)
            self.assertFalse(result['allocation_within_current_free_limits']);self.assertEqual(result['status'],'pilot-held')
    def test_capacity_or_active_application_stops_pilot(self):
        for change in ({'available_memory_mib':1024},{'private_scratch_free_bytes':6*1024**3},{'all_guard_units_inactive':False}):
            self.assertEqual(assess(self.report()|change)['status'],'pilot-held')
    def test_ready_result_is_admission_only_not_execution_or_billing_proof(self):
        result=assess(self.report())
        self.assertEqual(result['status'],'dependencies-ready-for-private-pilot')
        self.assertFalse(result['pilot_executed']);self.assertFalse(result['account_billing_polled'])
        self.assertLess(result['max_monthly_ocpu_hours'],1500);self.assertLess(result['max_monthly_memory_gib_hours'],9000)
    def test_remote_mutations_or_external_calls_cannot_be_misreported_read_only(self):
        for change in ({'server_modified':True},{'b2_calls':1},{'global_installations':True}):
            with self.assertRaises(ValueError):assess(self.report()|change)

    def test_unexpected_remote_fields_are_not_forwarded_to_logs(self):
        with self.assertRaises(ValueError):assess(self.report()|{'unreviewed_output':'must-not-be-forwarded'})
