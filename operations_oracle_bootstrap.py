"""Explicit existing-host bootstrap over pinned SSH. No cloud provisioning."""
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
from operations_oracle_ssh_probe import run_pinned_command, HostSetupError

ROOT = Path(__file__).parent


def validate_authorization(data, evidence, env):
    expected = {'schema': 1, 'scope': 'existing-oracle-host-os-and-private-runtime-preparation',
                'host': '92.5.89.125', 'region': 'eu-frankfurt-1', 'shape': 'VM.Standard.A1.Flex',
                'ocpus': 1, 'memory_gib': 6, 'boot_gb': 47,
                'owner_confirmed_only_these_resources': True,
                'oracle_eligibility_verified_from_combined_evidence': True,
                'full_31_day_projection_ocpu_hours': 744,
                'full_31_day_projection_memory_gib_hours': 4464,
                'new_cloud_resources_authorized': False, 'public_access_authorized': False,
                'external_backup_activation_authorized': False, 'ai_calls_authorized': False}
    if type(data) is not dict or set(data) != set(expected) | {'evidence_sha256'}:
        raise ValueError('Complete host-only authorization required')
    if any(type(data[k]) is not type(value) or data[k] != value for k, value in expected.items()):
        raise ValueError('Unreviewed host scope/allocation')
    if data['evidence_sha256'] != hashlib.sha256(evidence).hexdigest():
        raise ValueError('Owner evidence changed')
    if env.get('FG_OCI_HOST') != data['host'] or env.get('GITHUB_REF') != 'refs/heads/filip-guard-development' or env.get('GITHUB_REPOSITORY') != 'Ciobanu87/filip-guard':
        raise ValueError('Wrong host, repository or branch')
    if env.get('FG_OCI_HOST_SETUP_AUTHORIZED') != '1': raise ValueError('Host changes not authorized')
    return data


def main():
    phase = 'authorization'
    try:
        evidence = (ROOT / 'deployment/oracle-prepared/owner-evidence-20261126.json').read_bytes()
        data = validate_authorization(json.loads((ROOT / 'deployment/oracle-host-setup-request.json').read_text()), evidence, os.environ)
        commit = os.environ['GITHUB_SHA']
        if not re.fullmatch('[0-9a-f]{40}', commit): raise ValueError('Immutable development snapshot required')
        archive = subprocess.check_output(['git', 'archive', '--format=tar', commit], cwd=ROOT)
        if len(archive) > 16 * 1024 * 1024: raise ValueError('Source too large')
        source = (ROOT / 'deployment/oracle_host_bootstrap.py').read_text()
        digest = hashlib.sha256(archive).hexdigest()
        command = 'sudo -n -- /usr/bin/python3 -c ' + shlex.quote(source) + ' ' + commit + ' ' + digest + ' ' + data['evidence_sha256']
        phase = 'remote-setup'
        report = json.loads(run_pinned_command(command, operation='host-setup', input_data=archive, timeout=900))
        allowed = {'status', 'server_modified', 'source_snapshot_verified', 'python311_installed',
                   'dependencies_imported_as_nonroot', 'public_scanner_ui_render_verified', 'loopback_health_verified',
                   'persistent_state_unchanged', 'services_enabled', 'external_backup_enabled',
                   'customer_state_initialized', 'ai_ledger_initialized', 'new_cloud_resources', 'groq_calls'}
        if type(report) is not dict or set(report) != allowed or report['status'] != 'host-runtime-prepared':
            raise ValueError('Host verification incomplete')
        for key in allowed - {'status', 'new_cloud_resources', 'groq_calls'}:
            if type(report[key]) is not bool: raise ValueError('Unexpected host flag')
        if not all(report[k] for k in ('server_modified', 'source_snapshot_verified', 'python311_installed',
                    'dependencies_imported_as_nonroot', 'public_scanner_ui_render_verified', 'loopback_health_verified',
                    'persistent_state_unchanged')): raise ValueError('Host validation incomplete')
        if any(type(report[k]) is not int for k in ('new_cloud_resources', 'groq_calls')): raise ValueError('Invalid operation count')
        if any(report[k] for k in ('services_enabled', 'external_backup_enabled', 'customer_state_initialized', 'ai_ledger_initialized', 'new_cloud_resources', 'groq_calls')):
            raise ValueError('Unreviewed activation')
    except HostSetupError as exc:
        print(json.dumps({'status': 'blocked-or-failed', 'phase': phase, 'remote_phase': exc.phase,
                          'server_may_be_modified': True, 'groq_calls': 0})); return 1
    except Exception:
        print(json.dumps({'status': 'blocked-or-failed', 'phase': phase,
                          'server_may_be_modified': phase == 'remote-setup', 'groq_calls': 0}))
        return 1
    print(json.dumps(report, sort_keys=True)); return 0


if __name__ == '__main__': raise SystemExit(main())
