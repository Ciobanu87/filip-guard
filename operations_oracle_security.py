"""Sequential pinned SSH hardening, independent reconnect and reboot validation."""
import json
import os
from pathlib import Path
import shlex
import time

from operations_oracle_bootstrap import validate_authorization
from operations_oracle_ssh_probe import run_pinned_command

ROOT = Path(__file__).parent


def action(name):
    source = (ROOT / 'deployment/oracle_host_security.py').read_text()
    command = 'sudo -n -- /usr/bin/python3 -c ' + shlex.quote(source) + ' ' + name + ' "$SSH_CONNECTION"'
    data = json.loads(run_pinned_command(command, operation='host-setup', timeout=90))
    if type(data) is not dict or len(json.dumps(data)) > 2048:
        raise ValueError('Unexpected host response')
    return data


def main():
    phase = 'authorization'
    try:
        evidence = (ROOT / 'deployment/oracle-prepared/owner-evidence-20261126.json').read_bytes()
        validate_authorization(json.loads((ROOT / 'deployment/oracle-host-setup-request.json').read_text()), evidence, os.environ)
        phase = 'ssh-hardening'
        report = action('apply')
        if report.get('status') not in ('ssh-already-confirmed', 'ssh-hardened-pending-second-connection'):
            raise ValueError('SSH hardening did not complete')
        phase = 'second-connection'
        report = action('confirm')
        if report.get('status') != 'ssh-hardening-confirmed' or report.get('second_pinned_connection_verified') is not True:
            raise ValueError('Second connection did not verify')
        phase = 'controlled-reboot'
        report = action('reboot')
        if report.get('status') not in ('reboot-requested', 'reboot-already-observed'):
            raise ValueError('Reboot request not verified')
        phase = 'post-reboot-validation'
        # Reconnect attempts are bounded; each independently checks the host pin
        # before using the key. No application/provider verification is repeated.
        deadline = time.monotonic() + 240
        while True:
            try:
                report = action('validate')
                required = {'reboot_observed', 'root_login_disabled', 'second_pinned_connection_verified',
                            'private_state_unchanged', 'durability_proof_survived', 'selinux_enforcing', 'firewalld_active'}
                if report.get('status') != 'reboot-and-private-persistence-verified' or any(report.get(k) is not True for k in required):
                    raise ValueError('Host validation not complete')
                if any(report.get(k) is not False for k in ('services_enabled', 'external_backup_enabled')):
                    raise ValueError('Unreviewed service activation')
                if report.get('new_cloud_resources') != 0 or report.get('groq_calls') != 0:
                    raise ValueError('Unreviewed external action')
                break
            except Exception:
                if time.monotonic() >= deadline: raise
                time.sleep(5)
    except Exception:
        print(json.dumps({'status': 'host-security-or-reboot-unverified', 'phase': phase,
                          'server_may_be_modified': phase != 'authorization', 'groq_calls': 0})); return 1
    print(json.dumps(report, sort_keys=True)); return 0


if __name__ == '__main__': raise SystemExit(main())
