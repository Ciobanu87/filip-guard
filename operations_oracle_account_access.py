"""Pinned SSH entry point for fixed, read-only existing OCI identity discovery."""
import json
from pathlib import Path
from operations_oracle_ssh_probe import run_pinned_command

BOOLEAN_FIELDS = {'sdk_available', 'cli_available', 'existing_identity_read_authorized',
                  'home_region_frankfurt_verified', 'region_list_complete',
                  'account_resource_inventory_verified', 'cumulative_usage_verified',
                  'server_modified', 'iam_permissions_changed'}
STATUSES = {'no-existing-account-tooling', 'account-region-list-incomplete',
            'account-home-region-unverified', 'existing-identity-region-read-succeeded',
            'existing-cli-needs-tenancy-scope', 'existing-identity-read-unavailable'}


def validate(data):
    if type(data) is not dict or set(data) != BOOLEAN_FIELDS | {'schema', 'region_subscription_count', 'groq_calls', 'status'}:
        raise ValueError('Unexpected account-access schema')
    if any(type(data[key]) is not bool for key in BOOLEAN_FIELDS):
        raise ValueError('Unexpected account-access flag')
    if type(data['schema']) is not int or data['schema'] != 1 or type(data['groq_calls']) is not int or data['groq_calls'] != 0:
        raise ValueError('Unreviewed account operation')
    if type(data['region_subscription_count']) is not int or not 0 <= data['region_subscription_count'] <= 100:
        raise ValueError('Unexpected region count')
    if data['status'] not in STATUSES or any(data[k] for k in (
            'account_resource_inventory_verified', 'cumulative_usage_verified', 'server_modified', 'iam_permissions_changed')):
        raise ValueError('Invalid account-wide verification claim')
    return data


def main():
    source = Path(__file__).with_name('deployment').joinpath('oracle_account_access_inspect.py').read_text()
    command = "python3 - <<'FG_ACCOUNT_READ_ONLY'\n" + source + '\nFG_ACCOUNT_READ_ONLY'
    try:
        report = validate(json.loads(run_pinned_command(command)))
    except Exception:
        print('{"status":"ssh-or-probe-unverified","server_modified":false}')
        return 1
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == '__main__': raise SystemExit(main())
