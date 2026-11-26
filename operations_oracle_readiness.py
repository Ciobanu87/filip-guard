"""Prepare inactive units and verify native host behavior without deferred gates."""
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess

from operations_oracle_bootstrap import validate_authorization
from operations_oracle_ssh_probe import run_pinned_command, HostSetupError

ROOT = Path(__file__).parent
BASELINE = 'a4fa538af200a78896faef1ab7d2143a95309e8d'


def main():
    try:
        request_scope = json.loads((ROOT / 'deployment/oracle-operations-readiness-request.json').read_text())
        expected_scope = {'authorized': True, 'requested_on': '2026-11-26',
                          'scope': 'inactive-unit-preparation-and-isolated-native-host-stability',
                          'systemd_service_activation': False, 'provider_requests': 0,
                          'master_key_operations': False, 'groq_calls': 0}
        if request_scope != expected_scope or any(type(request_scope[k]) is not type(v) for k, v in expected_scope.items()):
            raise ValueError('Explicit held-runtime-only request required')
        evidence = (ROOT / 'deployment/oracle-prepared/owner-evidence-20261126.json').read_bytes()
        approved = validate_authorization(json.loads((ROOT / 'deployment/oracle-host-setup-request.json').read_text()), evidence, os.environ)
        names = ('filip-guard-ui.service', 'filip-guard-worker.service')
        units = {name: (ROOT / 'deployment/oracle-prepared' / (name + '.example')).read_text() for name in names}
        previous = {name: hashlib.sha256(subprocess.check_output(['git', 'show', BASELINE + ':deployment/oracle-prepared/' + name + '.example'], cwd=ROOT)).hexdigest() for name in names}
        request = {'evidence_sha256': approved['evidence_sha256'], 'units': units, 'previous_sha256': previous,
                   'harness': (ROOT / 'tests/host_operations/readiness.py').read_text()}
        source = (ROOT / 'deployment/oracle_operations_readiness.py').read_text()
        response = json.loads(run_pinned_command('sudo -n -- /usr/bin/python3 -c ' + shlex.quote(source),
                                                operation='host-setup', input_data=json.dumps(request).encode(), timeout=240))
        if response.get('status') != 'native-host-isolated-readiness-verified' or response.get('activation_gate_still_blocks') is not True or response.get('original_state_unchanged') is not True:
            raise ValueError('Host readiness not verified')
        if any(response.get(key) != 0 for key in ('groq_calls', 'provider_requests', 'master_key_operations')) or response.get('services_enabled') is not False:
            raise ValueError('Unexpected provider/service operation')
    except HostSetupError as exc:
        print(json.dumps({'status': 'operations-readiness-blocked-or-failed', 'remote_phase': exc.phase,
                          'services_enabled': False, 'groq_calls': 0})); return 1
    except Exception:
        print('{"status":"operations-readiness-blocked-or-failed","services_enabled":false,"groq_calls":0}'); return 1
    print(json.dumps(response, sort_keys=True)); return 0


if __name__ == '__main__': raise SystemExit(main())
