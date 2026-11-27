from datetime import datetime, timedelta, timezone
import io
import json
from pathlib import Path
import tempfile
import subprocess
import unittest
from unittest.mock import patch

import operations_host_gate as gate
import operations_scheduled_state_backup as backup
from deployment.oracle_host_inspect import inspect
from operations_oracle_inventory import validate_inventory


NOW = datetime(2026, 11, 26, 14, tzinfo=timezone.utc)


def approval():
    # Synthetic approval for local tests; never written to the host or committed
    # as an operational approval file.
    return dict(always_free_verified=True, installation_authorized=True,
                image_always_free=True, volume_performance_always_free=True,
                all_regions_reviewed=True, b2_zero_spend_cap_verified=True,
                host='92.5.89.125', home_region='eu-frankfurt-1',
                shape='VM.Standard.A1.Flex', ocpus=1, memory_gib=6,
                aggregate_a1_ocpu_hours=744, aggregate_a1_memory_gib_hours=4464,
                aggregate_boot_block_gib=47, aggregate_volume_backups=0,
                billable_cost=0, b2_free_remaining_bytes=gate.MAX_OBJECT_BYTES * 8,
                evidence_sha256='a' * 64, reviewed_at=NOW.isoformat(),
                expires_at=(NOW + timedelta(days=7)).isoformat())


class HostApprovalTests(unittest.TestCase):
    def test_approval_rejects_expired_future_incomplete_or_billable_evidence(self):
        valid = approval()
        self.assertEqual(gate.validate_approval(valid, NOW), valid)
        for change in ({'billable_cost': 0.01}, {'aggregate_boot_block_gib': 201},
                       {'aggregate_a1_ocpu_hours': 1501}, {'aggregate_a1_memory_gib_hours': 9001},
                       {'aggregate_volume_backups': 6}, {'all_regions_reviewed': False},
                       {'b2_zero_spend_cap_verified': False}, {'image_always_free': False},
                       {'volume_performance_always_free': False}, {'installation_authorized': False},
                       {'ocpus': True}, {'billable_cost': float('nan')}, {'billable_cost': False},
                       {'expires_at': NOW.isoformat()}, {'reviewed_at': (NOW + timedelta(minutes=1)).isoformat()},
                       {'home_region': 'us-ashburn-1'}, {'host': '8.8.8.8'}, {'evidence_sha256': ''},
                       {'expires_at': (NOW + timedelta(days=8)).isoformat()},
                       {'b2_free_remaining_bytes': 0}):
            with self.subTest(change=change), self.assertRaises((ValueError, TypeError)):
                gate.validate_approval({**valid, **change}, NOW)
        template = json.loads(Path('deployment/oracle-prepared/host-approval.json.example').read_text())
        with self.assertRaises(ValueError): gate.validate_approval(template, NOW)

    def test_no_execute_flag_has_no_gate_credentials_subprocess_or_writes(self):
        with patch.object(backup, 'run_backup') as execute, patch('sys.stdout', new_callable=io.StringIO) as output:
            self.assertEqual(backup.main([]), 0)
        execute.assert_not_called()
        self.assertFalse(json.loads(output.getvalue())['server_modified'])

    def test_missing_account_approval_blocks_before_service_or_export(self):
        with patch.object(backup, 'host_gate', side_effect=ValueError('not approved')), \
             patch.object(backup, 'control') as services, patch.object(backup.subprocess, 'run') as process, \
             patch('sys.stdout', new_callable=io.StringIO):
            self.assertEqual(backup.main(['--execute']), 1)
        services.assert_not_called(); process.assert_not_called()

    def test_host_gate_rejects_state_path_drift_before_database_access(self):
        with patch.object(gate, 'read_root_file', return_value=json.dumps(approval())), \
             patch.object(gate, 'validate_approval', return_value=approval()), \
             patch('runtime_state.require_existing_guard_state') as database:
            with self.assertRaises(ValueError): gate.host_gate({})
        database.assert_not_called()

    def test_missing_original_ai_ledger_blocks_start_without_recreating_it(self):
        env = {'FG_CUSTOMER_AUTH_DB': str(gate.STATE / 'accounts.sqlite'),
               'FG_CUSTOMER_DATA_ROOT': str(gate.STATE / 'sites'),
               'FG_MONITOR_DB': str(gate.STATE / 'monitor.sqlite'),
               'FG_AI_LEDGER_DB': str(gate.STATE / 'advisor.sqlite')}
        with patch.object(gate, 'read_root_file', return_value=json.dumps(approval())), \
             patch.object(gate, 'validate_approval', return_value=approval()), \
             patch('runtime_state.require_existing_guard_state'), \
             patch('advisor_ledger.require_existing_advisor_ledger', side_effect=ValueError('missing original ledger')) as ledger:
            with self.assertRaises(ValueError): gate.host_gate(env)
        ledger.assert_called_once_with(gate.STATE / 'advisor.sqlite')


class BackupLifecycleTests(unittest.TestCase):
    def control(self, state, events):
        def call(action, unit):
            events.append((action, unit))
            if action == 'status': return state[unit]
            state[unit] = 'inactive' if action == 'stop' else 'active'
        return call

    def test_stops_both_writers_before_export_and_preserves_prior_running_set(self):
        for before in ({backup.UNITS[0]: 'active', backup.UNITS[1]: 'active'},
                       {backup.UNITS[0]: 'active', backup.UNITS[1]: 'inactive'},
                       {unit: 'inactive' for unit in backup.UNITS}):
            state = dict(before); events = []
            def check():
                self.assertTrue(all(value == 'inactive' for value in state.values()))
                events.append(('quiesced', ''))
            def export():
                self.assertEqual(events[-1][0], 'quiesced')
                self.assertTrue(all(value == 'inactive' for value in state.values()))
                events.append(('export', ''))
            backup.backup_cycle(self.control(state, events), export, check)
            self.assertEqual(state, before)
            for unit, previous in before.items():
                if previous == 'inactive': self.assertNotIn(('start', unit), events)

    def test_upload_or_recovery_failure_resumes_original_services_and_fails(self):
        before = {unit: 'active' for unit in backup.UNITS}; state = dict(before)
        def failed_export(): raise ValueError('unverified external readback')
        with self.assertRaises(ValueError):
            backup.backup_cycle(self.control(state, []), failed_export, lambda: None)
        self.assertEqual(state, before)

    def test_uncertain_stop_or_extra_process_never_exports(self):
        for extra_writer in (False, True):
            state = {unit: 'active' for unit in backup.UNITS}; events = []
            control = self.control(state, events)
            def stopping(action, unit):
                value = control(action, unit)
                if not extra_writer and action == 'stop': raise TimeoutError()
                return value
            def check(): raise ValueError('unmanaged writer')
            with patch('builtins.print') as exported, self.assertRaises((TimeoutError, ValueError)):
                backup.backup_cycle(stopping, exported, check)
            exported.assert_not_called()
            self.assertTrue(all(value == 'active' for value in state.values()))

    def test_restart_failure_is_reported_even_if_export_succeeded(self):
        state = {unit: 'active' for unit in backup.UNITS}
        control = self.control(state, [])
        def failing(action, unit):
            if action == 'start': raise RuntimeError('service startup failed')
            return control(action, unit)
        with self.assertRaisesRegex(RuntimeError, 'resume'):
            backup.backup_cycle(failing, lambda: None, lambda: None)

    def test_export_timeout_kills_and_reaps_process_group_before_returning(self):
        with patch.object(backup.subprocess, 'Popen') as spawn, patch.object(backup.os, 'killpg') as kill:
            process = spawn.return_value
            process.pid = 123456
            process.communicate.side_effect = [subprocess.TimeoutExpired('export', 240), (b'', b'')]
            with self.assertRaises(subprocess.TimeoutExpired): backup.run_export_command(['synthetic-export'])
            kill.assert_called_once_with(123456, backup.signal.SIGKILL)
            self.assertEqual(process.communicate.call_count, 2)
            self.assertTrue(spawn.call_args.kwargs['start_new_session'])


class BackupAllowanceTests(unittest.TestCase):
    def test_attempt_reserved_durably_and_never_refunded_or_repeated_same_day(self):
        with tempfile.TemporaryDirectory() as directory:
            quota = Path(directory) / 'reservations.json'
            quota.write_text('{"schema":1,"attempts":[]}'); quota.chmod(0o600)
            with patch.object(backup, 'QUOTA', quota), patch.object(backup, 'read_root_file', side_effect=lambda p: p.read_bytes()):
                backup.reserve_attempt(approval(), NOW)
                self.assertEqual(len(json.loads(quota.read_text())['attempts']), 1)
                with self.assertRaises(ValueError): backup.reserve_attempt(approval(), NOW)
                for day in range(1, 7): backup.reserve_attempt(approval(), NOW + timedelta(days=day))
                with self.assertRaises(ValueError): backup.reserve_attempt(approval(), NOW + timedelta(days=7))
                self.assertEqual(len(json.loads(quota.read_text())['attempts']), 7)

    def test_missing_reservation_journal_is_never_initialized(self):
        with patch.object(backup, 'read_root_file', side_effect=FileNotFoundError()):
            with self.assertRaises(FileNotFoundError): backup.reserve_attempt(approval(), NOW)


class InventoryContractTests(unittest.TestCase):
    def test_remote_schema_is_allowlisted_and_never_treated_as_billing_proof(self):
        # Local read-only collection only; the real Oracle result is checked by CI.
        with patch('deployment.oracle_host_inspect.command', return_value=''):
            report = inspect()
        validate_inventory(report)
        self.assertFalse(report['server_modified']); self.assertFalse(report['always_free_billing_verified'])
        for change in ({'root_login': 'secret text'}, {'extra': 'credential'},
                       {'groq_calls': 1}, {'always_free_billing_verified': True},
                       {'logical_cpus': True}, {'memory_mib': -1}, {'state_filesystem': 'unknown-text'}):
            with self.assertRaises(ValueError): validate_inventory({**report, **change})


if __name__ == '__main__': unittest.main()
