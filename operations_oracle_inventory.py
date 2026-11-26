"""Authorized fixed read-only inventory through the existing pinned transport."""
import json
from pathlib import Path
from operations_oracle_ssh_probe import run_pinned_command

BOOLEAN_FIELDS = {
    'oracle_linux_9', 'arm64', 'systemd_available', 'python311_available',
    'podman_available', 'docker_available', 'password_authentication_disabled',
    'public_key_authentication_enabled', 'selinux_enforcing', 'firewalld_active',
    'state_directory_exists', 'state_directory_symlink', 'existing_guard_ui_active',
    'existing_guard_worker_active', 'always_free_billing_verified', 'server_modified',
}
INTEGER_FIELDS = {'schema', 'logical_cpus', 'memory_mib', 'state_filesystem_total_gib',
                  'state_filesystem_available_gib', 'groq_calls'}


def validate_inventory(data):
    if type(data) is not dict or set(data) != BOOLEAN_FIELDS | INTEGER_FIELDS | {'root_login', 'state_filesystem'}:
        raise ValueError('Unexpected inventory schema')
    if any(type(data[key]) is not bool for key in BOOLEAN_FIELDS):
        raise ValueError('Invalid inventory boolean')
    if any(type(data[key]) is not int or not 0 <= data[key] <= 10**9 for key in INTEGER_FIELDS):
        raise ValueError('Invalid inventory number')
    if data['root_login'] not in ('yes', 'no', 'prohibit-password', 'without-password', 'forced-commands-only', 'unknown'):
        raise ValueError('Invalid SSH setting')
    if data['state_filesystem'] not in ('xfs', 'ext4', 'btrfs', 'tmpfs', 'overlay', 'nfs', 'nfs4', 'other'):
        raise ValueError('Invalid filesystem')
    if data['schema'] != 1 or data['server_modified'] or data['always_free_billing_verified'] or data['groq_calls'] != 0:
        raise ValueError('Invalid read-only claim')
    return data


def run_inventory(env=None, runner=None):
    source = Path(__file__).with_name('deployment').joinpath('oracle_host_inspect.py').read_text()
    remote = "python3 - <<'FG_READONLY_INVENTORY'\n" + source + '\nFG_READONLY_INVENTORY'
    return validate_inventory(json.loads(run_pinned_command(remote, env, runner)))


if __name__ == '__main__':
    try:
        report = run_inventory()
    except Exception:
        print(json.dumps({'status': 'blocked', 'server_modified': False, 'always_free_billing_verified': False}))
        raise SystemExit(1)
    print(json.dumps({'status': 'read-only-inventory-verified', **report}, sort_keys=True))
