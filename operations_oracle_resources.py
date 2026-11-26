"""Fixed pinned-SSH current allocation discovery; no provisioning or installation."""
import json
from pathlib import Path
from operations_oracle_ssh_probe import run_pinned_command


def validate(data):
    fields = {'schema', 'api_http_status', 'status', 'blocked_step', 'scope', 'core_allocation_inventory_verified',
              'compartments_checked', 'a1_instances', 'other_instances', 'a1_ocpus', 'a1_memory_gib',
              'boot_volume_gib', 'block_volume_gib', 'volume_backup_count', 'historical_usage_verified',
              'all_service_costs_verified', 'server_modified', 'iam_permissions_changed', 'groq_calls'}
    if type(data) is not dict or set(data) != fields: raise ValueError('Unexpected inventory')
    booleans = {'core_allocation_inventory_verified', 'historical_usage_verified', 'all_service_costs_verified',
                'server_modified', 'iam_permissions_changed'}
    if any(type(data[k]) is not bool for k in booleans): raise ValueError('Unexpected flag')
    numbers = {'schema', 'compartments_checked', 'a1_instances', 'other_instances', 'a1_ocpus', 'a1_memory_gib',
               'boot_volume_gib', 'block_volume_gib', 'volume_backup_count', 'groq_calls'}
    if any(type(data[k]) not in (int, float) or not 0 <= data[k] <= 10**9 for k in numbers):
        raise ValueError('Unexpected count')
    if data['status'] not in ('blocked', 'current-core-allocations-read') or data['blocked_step'] not in (
            'sdk-or-identity', 'region-subscriptions', 'compartment-list', 'availability-domain-list',
            'instance-list', 'boot-volume-list', 'block-volume-list', 'volume-backup-list', 'none'):
        raise ValueError('Unexpected status')
    if type(data['api_http_status']) is not int or not (data['api_http_status'] == 0 or 100 <= data['api_http_status'] <= 599):
        raise ValueError('Unexpected HTTP status')
    if data['scope'] != 'current-compute-boot-block-and-volume-backups' or data['schema'] != 1 or data['groq_calls'] != 0:
        raise ValueError('Unexpected scope')
    if any(data[k] for k in booleans - {'core_allocation_inventory_verified'}):
        raise ValueError('Invalid complete-account claim')
    if data['core_allocation_inventory_verified'] != (data['status'] == 'current-core-allocations-read' and data['blocked_step'] == 'none'):
        raise ValueError('Incomplete inventory cannot pass')
    return data


def main():
    source = Path(__file__).with_name('deployment').joinpath('oracle_resource_inspect.py').read_text()
    try:
        report = validate(json.loads(run_pinned_command("python3 - <<'FG_CORE_READ_ONLY'\n" + source + '\nFG_CORE_READ_ONLY')))
    except Exception:
        print('{"status":"ssh-or-probe-unverified","server_modified":false}')
        return 1
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == '__main__': raise SystemExit(main())
